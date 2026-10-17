// SPDX-License-Identifier: BSD-3-Clause

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include "geometry_msgs/msg/twist.hpp"
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_srvs/srv/set_bool.hpp"
#include "tf2/LinearMath/Matrix3x3.hpp"
#include "tf2/LinearMath/Quaternion.hpp"
#include "tf2/LinearMath/Vector3.hpp"
#include "tf2_ros/transform_broadcaster.hpp"

class Lite3MotionNode : public rclcpp::Node
{
public:
    Lite3MotionNode()
        : Node("lite3_motion_node")
    {
        // 发送到本机速度接收端；这里没有指定接收程序的名字。
        velocity_socket_ = ::socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
        if (velocity_socket_ < 0)
        {
            throw std::runtime_error(
                std::string("创建速度发送接口失败：") + std::strerror(errno));
        }

        velocity_destination_.sin_family = AF_INET;
        velocity_destination_.sin_port = htons(30011);
        velocity_destination_.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

        cmd_vel_subscription_ =
            create_subscription<geometry_msgs::msg::Twist>(
                "/cmd_vel", 10,
                [this](geometry_msgs::msg::Twist::ConstSharedPtr message)
                {
                    ReceiveVelocity(*message, false);
                });

        nav_cmd_vel_subscription_ =
            create_subscription<geometry_msgs::msg::Twist>(
                "/nav_cmd_vel", 10,
                [this](geometry_msgs::msg::Twist::ConstSharedPtr message)
                {
                    ReceiveVelocity(*message, true);
                });

        navigation_mode_service_ =
            create_service<std_srvs::srv::SetBool>(
                "/lite3/set_navigation_mode",
                [this](
                    std::shared_ptr<std_srvs::srv::SetBool::Request> request,
                    std::shared_ptr<std_srvs::srv::SetBool::Response> response)
                {
                    navigation_mode_ = request->data;
                    ClearVelocity();

                    response->success = true;
                    response->message = navigation_mode_
                        ? "已切换到导航模式，当前速度已清零"
                        : "已切换到手动模式，当前速度已清零";
                    if (stop_locked_)
                    {
                        response->message += "；停止锁定仍然有效";
                    }
                    RCLCPP_INFO(
                        get_logger(), "%s", response->message.c_str());
                });

        stop_service_ =
            create_service<std_srvs::srv::SetBool>(
                "/lite3/set_stop",
                [this](
                    std::shared_ptr<std_srvs::srv::SetBool::Request> request,
                    std::shared_ptr<std_srvs::srv::SetBool::Response> response)
                {
                    stop_locked_ = request->data;
                    ClearVelocity();

                    response->success = true;
                    response->message = stop_locked_
                        ? "停止锁定已开启，拒绝所有速度指令"
                        : "停止锁定已解除，等待新的速度指令";
                    RCLCPP_INFO(
                        get_logger(), "%s", response->message.c_str());
                });

        navigation_pause_service_ = create_service<std_srvs::srv::SetBool>(
            "/lite3/set_navigation_pause",
            [this](std_srvs::srv::SetBool::Request::SharedPtr request,
                   std_srvs::srv::SetBool::Response::SharedPtr response)
            {
                navigation_paused_ = request->data;
                ClearVelocity();
                response->success = true;
                response->message = navigation_paused_
                    ? "导航内部暂停，导航速度已清零；用户停止锁定保持原样"
                    : "导航内部暂停已解除，等待新速度；用户停止锁定保持原样";
                RCLCPP_INFO(get_logger(), "%s", response->message.c_str());
            });

        odometry_publisher_ = create_publisher<nav_msgs::msg::Odometry>(
            "/odom", 10);
        transform_broadcaster_ =
            std::make_unique<tf2_ros::TransformBroadcaster>(*this);

        // 接收三维机身真值，整理为平面导航状态与保留机身倾斜的 TF。
        ground_truth_subscription_ =
            create_subscription<nav_msgs::msg::Odometry>(
                "/lite3/ground_truth/odom", 10,
                [this](nav_msgs::msg::Odometry::ConstSharedPtr message)
                {
                    PublishOdometryAndTransforms(*message);
                });

        timeout_timer_ = create_wall_timer(
            std::chrono::milliseconds(50),
            [this]()
            {
                if (have_command_)
                {
                    const auto elapsed =
                        std::chrono::steady_clock::now() - last_command_time_;
                    if (elapsed >= std::chrono::milliseconds(500))
                    {
                        target_velocity_ = geometry_msgs::msg::Twist{};
                        have_command_ = false;
                        RCLCPP_WARN(
                            get_logger(),
                            "超过 0.5 秒没有新指令，目标速度已归零");
                    }
                }

                // 没有指令或已经超时时，也持续发送零速度。
                SendVelocity();
            });

        RCLCPP_INFO(
            get_logger(),
            "运动节点已启动，默认手动模式：手动 /cmd_vel，导航 /nav_cmd_vel；"
            "模式服务 /lite3/set_navigation_mode，停止服务 /lite3/set_stop；"
            "发布 /odom 和机身 TF，保留 20 Hz UDP 发送与 0.5 秒速度超时保护");
    }

    ~Lite3MotionNode() override
    {
        if (velocity_socket_ >= 0)
        {
            // 正常退出时尽力发送一次零速度；接收端仍需自己的断线保护。
            target_velocity_ = geometry_msgs::msg::Twist{};
            SendVelocity();
            ::close(velocity_socket_);
        }
    }

private:
    void ClearVelocity()
    {
        target_velocity_ = geometry_msgs::msg::Twist{};
        have_command_ = false;
        SendVelocity();
    }

    void ReceiveVelocity(
        const geometry_msgs::msg::Twist &message,
        bool from_navigation)
    {
        // 非当前来源和锁定期间的消息均不改变目标，也不刷新超时计时。
        if (stop_locked_ || from_navigation != navigation_mode_ ||
            (from_navigation && navigation_paused_))
        {
            RCLCPP_INFO_THROTTLE(
                get_logger(), *get_clock(), 2000,
                "忽略 %s：%s",
                from_navigation ? "/nav_cmd_vel" : "/cmd_vel",
                stop_locked_ ? "停止锁定中" :
                (from_navigation && navigation_paused_ ? "导航内部暂停中" : "不属于当前控制模式"));
            return;
        }

        if (!std::isfinite(message.linear.x) ||
            !std::isfinite(message.linear.y) ||
            !std::isfinite(message.angular.z))
        {
            ClearVelocity();
            RCLCPP_WARN(get_logger(), "速度包含无效数字，当前速度已清零");
            return;
        }

        // 只使用平面运动的三个分量；发送实际速度，不是归一化比例。
        target_velocity_.linear.x = std::clamp(message.linear.x, -0.8, 0.8);
        target_velocity_.linear.y = std::clamp(message.linear.y, -0.8, 0.8);
        target_velocity_.angular.z = std::clamp(message.angular.z, -0.8, 0.8);
        last_command_time_ = std::chrono::steady_clock::now();
        have_command_ = true;

        RCLCPP_INFO_THROTTLE(
            get_logger(), *get_clock(), 1000,
            "接受%s速度：前后 %.2f m/s，左右 %.2f m/s，转向 %.2f rad/s",
            from_navigation ? "导航" : "手动",
            target_velocity_.linear.x,
            target_velocity_.linear.y,
            target_velocity_.angular.z);
    }

    void PublishOdometryAndTransforms(const nav_msgs::msg::Odometry &message)
    {
        // 当前方案明确使用 Gazebo world 真值，TORSO 为实际机身。
        if (message.header.frame_id != "world" ||
            message.child_frame_id != "TORSO" ||
            message.header.stamp.sec < 0 ||
            message.header.stamp.nanosec >= 1000000000u)
        {
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 2000,
                "实际状态的坐标名称或时间戳不符合 world/TORSO 输入约定，跳过");
            return;
        }

        const auto &position = message.pose.pose.position;
        const auto &orientation = message.pose.pose.orientation;
        const auto &linear = message.twist.twist.linear;
        const auto &angular = message.twist.twist.angular;
        const std::array<double, 13> values{
            position.x, position.y, position.z,
            orientation.x, orientation.y, orientation.z, orientation.w,
            linear.x, linear.y, linear.z, angular.x, angular.y, angular.z
        };
        if (!std::all_of(values.begin(), values.end(),
                         [](double value) { return std::isfinite(value); }))
        {
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 2000,
                "实际位置或速度包含无效数字，跳过本次位置与 TF 发布");
            return;
        }

        tf2::Quaternion body_rotation(
            orientation.x, orientation.y, orientation.z, orientation.w);
        const double norm_squared = body_rotation.length2();
        if (!std::isfinite(norm_squared) || norm_squared < 1e-12)
        {
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 2000,
                "实际朝向的四元数无效，跳过本次位置与 TF 发布");
            return;
        }
        body_rotation.normalize();

        double roll = 0.0, pitch = 0.0, yaw = 0.0;
        tf2::Matrix3x3(body_rotation).getRPY(roll, pitch, yaw);
        const double cos_pitch = std::cos(pitch);
        if (std::abs(cos_pitch) < 1e-3)
        {
            RCLCPP_WARN_THROTTLE(
                get_logger(), *get_clock(), 2000,
                "机身接近竖直，无法可靠整理平面朝向，跳过本次发布");
            return;
        }

        tf2::Quaternion heading_rotation;
        heading_rotation.setRPY(0.0, 0.0, yaw);
        const tf2::Matrix3x3 body_to_world(body_rotation);
        const tf2::Vector3 world_linear =
            body_to_world * tf2::Vector3(linear.x, linear.y, linear.z);
        // 原始速度在倾斜机身轴上；先转世界轴，再转水平导航轴。
        const tf2::Vector3 navigation_linear =
            tf2::Matrix3x3(heading_rotation).transpose() * world_linear;
        const double yaw_rate =
            (std::sin(roll) * angular.y + std::cos(roll) * angular.z) /
            cos_pitch;
        if (!std::isfinite(navigation_linear.x()) ||
            !std::isfinite(navigation_linear.y()) || !std::isfinite(yaw_rate))
        {
            return;
        }

        nav_msgs::msg::Odometry odometry;
        odometry.header.stamp = message.header.stamp;
        odometry.header.frame_id = "odom";
        odometry.child_frame_id = "base_footprint";
        // 本阶段 odom 原点/轴与 Gazebo world 一致；导航参考投影在 z=0 平面。
        odometry.pose.pose.position.x = position.x;
        odometry.pose.pose.position.y = position.y;
        odometry.pose.pose.orientation.z = heading_rotation.z();
        odometry.pose.pose.orientation.w = heading_rotation.w();
        odometry.twist.twist.linear.x = navigation_linear.x();
        odometry.twist.twist.linear.y = navigation_linear.y();
        odometry.twist.twist.angular.z = yaw_rate;
        // 协方差保持默认零：这里是仿真真值，不是实机传感器误差估计。

        geometry_msgs::msg::TransformStamped navigation_transform;
        navigation_transform.header = odometry.header;
        navigation_transform.child_frame_id = "base_footprint";
        navigation_transform.transform.translation.x = position.x;
        navigation_transform.transform.translation.y = position.y;
        navigation_transform.transform.rotation = odometry.pose.pose.orientation;

        tf2::Quaternion body_relative_rotation =
            heading_rotation.inverse() * body_rotation;
        body_relative_rotation.normalize();
        geometry_msgs::msg::TransformStamped body_transform;
        body_transform.header.stamp = message.header.stamp;
        body_transform.header.frame_id = "base_footprint";
        body_transform.child_frame_id = "TORSO";
        body_transform.transform.translation.z = position.z;
        body_transform.transform.rotation.x = body_relative_rotation.x();
        body_transform.transform.rotation.y = body_relative_rotation.y();
        body_transform.transform.rotation.z = body_relative_rotation.z();
        body_transform.transform.rotation.w = body_relative_rotation.w();

        odometry_publisher_->publish(odometry);
        transform_broadcaster_->sendTransform(
            std::vector<geometry_msgs::msg::TransformStamped>{
                navigation_transform, body_transform});

        RCLCPP_INFO_THROTTLE(
            get_logger(), *get_clock(), 2000,
            "实际位置：x=%.3f m，y=%.3f m，z=%.3f m；"
            "已发布 /odom 和 odom→base_footprint→TORSO",
            position.x, position.y, position.z);
    }

    void SendVelocity()
    {
        if (velocity_socket_ < 0)
        {
            return;
        }

        static_assert(sizeof(float) == 4, "速度协议要求 32 位 float");
        // 本机协议：三个 float，共 12 字节，顺序为 vx、vy、wz。
        const std::array<float, 3> velocity{
            static_cast<float>(target_velocity_.linear.x),
            static_cast<float>(target_velocity_.linear.y),
            static_cast<float>(target_velocity_.angular.z)
        };

        const auto sent = ::sendto(
            velocity_socket_, velocity.data(), sizeof(velocity), MSG_DONTWAIT,
            reinterpret_cast<const sockaddr *>(&velocity_destination_),
            sizeof(velocity_destination_));

        if (sent < 0)
        {
            RCLCPP_ERROR_THROTTLE(
                get_logger(), *get_clock(), 2000,
                "发送速度失败：%s", std::strerror(errno));
        }
    }

    // 所有回调由 main 中的单线程 spin 串行执行。
    bool navigation_mode_ = false;
    bool stop_locked_ = false;
    bool navigation_paused_ = false;
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr
        nav_cmd_vel_subscription_;
    rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr
        navigation_mode_service_;
    rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr stop_service_;
    rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr navigation_pause_service_;

    geometry_msgs::msg::Twist target_velocity_{};
    std::chrono::steady_clock::time_point last_command_time_{};
    bool have_command_ = false;
    int velocity_socket_ = -1;
    sockaddr_in velocity_destination_{};
    rclcpp::TimerBase::SharedPtr timeout_timer_;
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr
        cmd_vel_subscription_;
    rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr
        ground_truth_subscription_;
    rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odometry_publisher_;
    std::unique_ptr<tf2_ros::TransformBroadcaster> transform_broadcaster_;
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    try
    {
        auto node = std::make_shared<Lite3MotionNode>();
        rclcpp::spin(node);
    }
    catch (const std::exception &error)
    {
        RCLCPP_FATAL(
            rclcpp::get_logger("lite3_motion_node"),
            "运动节点运行失败：%s", error.what());
        rclcpp::shutdown();
        return 1;
    }

    rclcpp::shutdown();
    return 0;
}

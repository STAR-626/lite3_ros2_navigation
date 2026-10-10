// SPDX-License-Identifier: BSD-3-Clause

#include <iostream>
#include <memory>
#include <algorithm>
#include <cmath>
#include <atomic>
#include <chrono>
#include <cstring>
#include <cerrno>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/msgs/odometry.pb.h>
#include <gz/msgs/Utility.hh>
#include <gz/transport/Node.hh>

#include <gz/plugin/Register.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <array>
#include <string>
#include <vector>
#include <gz/sim/Joint.hh>
#include <gz/sim/Link.hh>
#include <gz/sim/components/Pose.hh>

namespace lite3_control
{

class Lite3GazeboInterface
    : public gz::sim::System,
      public gz::sim::ISystemConfigure,
      public gz::sim::ISystemPreUpdate,
      public gz::sim::ISystemPostUpdate
{
private:
    std::vector<gz::sim::Entity> joint_entities_;
    gz::sim::Entity body_entity_ = gz::sim::kNullEntity;
    unsigned int print_counter_ = 0;

    // 每条腿依次为侧摆髋关节、前后摆髋关节、膝关节，单位为弧度。
    const std::array<double, 3> stand_angles_{0.0, -0.65, 1.30};

    // 官方仿真接口协议：控制为 60 个 float，状态为 1 个 double + 45 个 float。
    // 顺序：Kp、目标角度、Kd、目标角速度、前馈力矩，各 12 个。
    std::array<float, 60> command_{};
    std::array<double, 12> applied_torque_{};
    int socket_ = -1;
    sockaddr_in controller_address_{};
    gz::transport::Node transport_;
    gz::transport::Node::Publisher ground_truth_publisher_;
    std::chrono::nanoseconds last_ground_truth_time_{0};
    bool have_ground_truth_time_ = false;
    std::atomic<int> requested_mode_{-1};
    bool external_mode_ = false;
    bool have_command_ = false;
    std::chrono::steady_clock::time_point last_command_{};

    void OnModeCommand(const gz::msgs::StringMsg &message)
    {
        if (message.data() == "stand") requested_mode_.store(0);
        else if (message.data() == "external") requested_mode_.store(1);
        else std::cerr << "[Lite3 control] Use stand or external." << std::endl;
    }

    void ReturnToStand(const char *reason)
    {
        external_mode_ = false;
        std::cout << "[Lite3 control] Mode: stand (" << reason << ")" << std::endl;
    }

    void ReceiveCommands()
    {
        if (socket_ < 0) return;
        for (int packet = 0; packet < 32; ++packet)
        {
            std::array<float, 60> incoming{};
            const auto received = recv(socket_, incoming.data(), sizeof(incoming),
                                       MSG_DONTWAIT | MSG_TRUNC);
            if (received < 0)
            {
                if (errno != EAGAIN && errno != EWOULDBLOCK)
                {
                    have_command_ = false;
                    if (external_mode_) ReturnToStand("socket receive error");
                }
                break;
            }
            bool valid = received == static_cast<ssize_t>(sizeof(incoming));
            for (const auto value : incoming) valid = valid && std::isfinite(value);
            for (std::size_t i = 0; i < 12; ++i)
            {
                valid = valid && incoming[i] >= 0.0f && incoming[i] <= 500.0f &&
                        incoming[24 + i] >= 0.0f && incoming[24 + i] <= 50.0f;
            }
            if (!valid)
            {
                have_command_ = false;
                if (external_mode_) ReturnToStand("invalid command, including NaN");
                continue;
            }
            command_ = incoming;
            have_command_ = true;
            last_command_ = std::chrono::steady_clock::now();
        }
    }

    void SendState(const gz::sim::UpdateInfo &info,
                   const gz::sim::EntityComponentManager &ecm)
    {
        if (socket_ < 0 || joint_entities_.size() != 12) return;
        const gz::sim::Link body(body_entity_);
        const auto pose = body.WorldPose(ecm);
        const auto omega = body.WorldAngularVelocity(ecm);
        const auto acceleration = body.WorldLinearAcceleration(ecm);
        if (!pose || !omega || !acceleration) return;
        const auto rpy = pose->Rot().Euler();
        const auto body_omega = pose->Rot().RotateVectorReverse(*omega);
        // 静止时 IMU 的加速度计应测到向上的重力支撑，不能只发送零加速度。
        const auto body_acc = pose->Rot().RotateVectorReverse(
            *acceleration - gz::math::Vector3d(0.0, 0.0, -9.81));
        std::array<float, 45> state{};
        for (std::size_t axis = 0; axis < 3; ++axis)
        {
            state[axis] = static_cast<float>(rpy[axis]);
            state[3 + axis] = static_cast<float>(body_acc[axis]);
            state[6 + axis] = static_cast<float>(body_omega[axis]);
        }
        for (std::size_t i = 0; i < 12; ++i)
        {
            const gz::sim::Joint joint(joint_entities_[i]);
            const auto position = joint.Position(ecm);
            const auto velocity = joint.Velocity(ecm);
            if (!position || position->empty() || !velocity || velocity->empty()) return;
            state[9 + i] = static_cast<float>(position->at(0));
            state[21 + i] = static_cast<float>(velocity->at(0));
            state[33 + i] = static_cast<float>(applied_torque_[i]);
        }
        for (const auto value : state) if (!std::isfinite(value)) return;
        static_assert(sizeof(float) == 4 && sizeof(double) == 8,
                      "Official UDP protocol requires 32-bit float and 64-bit double");
        // 手动拼接，避免结构体的内存对齐在末尾补字节。
        std::array<unsigned char, 188> packet{};
        const double timestamp = std::chrono::duration<double>(info.simTime).count();
        std::memcpy(packet.data(), &timestamp, sizeof(timestamp));
        std::memcpy(packet.data() + sizeof(timestamp), state.data(), sizeof(state));
        sendto(socket_, packet.data(), packet.size(), MSG_DONTWAIT,
               reinterpret_cast<const sockaddr *>(&controller_address_),
               sizeof(controller_address_));
    }

    void PublishGroundTruth(const gz::sim::UpdateInfo &info,
                            const gz::sim::EntityComponentManager &ecm)
    {
        if (!ground_truth_publisher_ ||
            body_entity_ == gz::sim::kNullEntity) return;

        const auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(
            info.simTime);
        if (have_ground_truth_time_ && now >= last_ground_truth_time_ &&
            now - last_ground_truth_time_ < std::chrono::milliseconds(20)) return;

        const gz::sim::Link body(body_entity_);
        const auto pose = body.WorldPose(ecm);
        const auto linear = body.WorldLinearVelocity(ecm);
        const auto angular = body.WorldAngularVelocity(ecm);
        if (!pose || !linear || !angular) return;
        if (!pose->Pos().IsFinite() || !pose->Rot().IsFinite() ||
            !linear->IsFinite() || !angular->IsFinite()) return;

        gz::msgs::Odometry message;
        const auto ns = now.count();
        auto *header = message.mutable_header();
        header->mutable_stamp()->set_sec(ns / 1000000000);
        header->mutable_stamp()->set_nsec(ns % 1000000000);

        auto *frame = header->add_data();
        frame->set_key("frame_id");
        frame->add_value("world");
        auto *child = header->add_data();
        child->set_key("child_frame_id");
        child->add_value("TORSO");

        gz::msgs::Set(message.mutable_pose(), *pose);
        gz::msgs::Set(message.mutable_twist()->mutable_linear(),
                     pose->Rot().RotateVectorReverse(*linear));
        gz::msgs::Set(message.mutable_twist()->mutable_angular(),
                     pose->Rot().RotateVectorReverse(*angular));
        ground_truth_publisher_.Publish(message);
        last_ground_truth_time_ = now;
        have_ground_truth_time_ = true;
    }

public:
    ~Lite3GazeboInterface() override
    {
        transport_.Unsubscribe("/lite3/control_mode");
        if (socket_ >= 0) close(socket_);
    }

    void Configure(
        const gz::sim::Entity &entity,
        const std::shared_ptr<const sdf::Element> &,
        gz::sim::EntityComponentManager &ecm,
        gz::sim::EventManager &) override
    {
        joint_entities_.clear();
        body_entity_ = gz::sim::kNullEntity;
        print_counter_ = 0;
        gz::sim::Model model(entity);

        if (!model.Valid(ecm))
        {
            std::cerr
                << "[Lite3 interface] Please attach this plugin to a model."
                << std::endl;
            return;
        }

        // TORSO 是 URDF 中的机身；开启状态计算，供后续 RL 使用。
        body_entity_ = model.LinkByName(ecm, "TORSO");
        if (body_entity_ == gz::sim::kNullEntity)
        {
            std::cerr << "[Lite3 interface] Missing body link: TORSO"
                      << std::endl;
            return;
        }

        gz::sim::Link body(body_entity_);
        body.EnableVelocityChecks(ecm);
        body.EnableAccelerationChecks(ecm);
        if (!ecm.Component<gz::sim::components::WorldPose>(body_entity_))
        {
            ecm.CreateComponent(
                body_entity_, gz::sim::components::WorldPose());
        }

        std::cout
            << "[Lite3 interface] Loaded for model: "
            << model.Name(ecm)
            << std::endl;
        const std::array<std::string, 12> joint_names = {
            "FL_HipX_joint", "FL_HipY_joint", "FL_Knee_joint",
            "FR_HipX_joint", "FR_HipY_joint", "FR_Knee_joint",
            "HL_HipX_joint", "HL_HipY_joint", "HL_Knee_joint",
            "HR_HipX_joint", "HR_HipY_joint", "HR_Knee_joint"
        };

        int found_count = 0;

        for (const auto &joint_name : joint_names)
        {
            const auto joint_entity =
                model.JointByName(ecm, joint_name);

            if (joint_entity == gz::sim::kNullEntity)
            {
                std::cerr
                    << "[Lite3 interface] Missing joint: "
                    << joint_name << std::endl;
            }
            else
            {
                ++found_count;
                joint_entities_.push_back(joint_entity);

                gz::sim::Joint joint(joint_entity);
                joint.EnablePositionCheck(ecm);
                joint.EnableVelocityCheck(ecm);
                std::cout
                    << "[Lite3 interface] Found joint: "
                    << joint_name << std::endl;
            }
        }

        std::cout
            << "[Lite3 interface] Joints found: "
            << found_count << "/12" << std::endl;

        // 全部关节确认成功后，才按顺序设置初始站姿。
        if (joint_entities_.size() != 12)
        {
            std::cerr << "[Lite3 interface] Standing control disabled: "
                      << "all 12 joints are required." << std::endl;
            return;
        }

        for (std::size_t i = 0; i < joint_entities_.size(); ++i)
        {
            gz::sim::Joint joint(joint_entities_[i]);
            joint.ResetPosition(ecm, {stand_angles_[i % 3]});
        }

        std::cout << "[Lite3 interface] Fixed standing controller ready."
                  << std::endl;

        socket_ = socket(AF_INET, SOCK_DGRAM, 0);
        sockaddr_in local{};
        local.sin_family = AF_INET;
        local.sin_port = htons(20001);
        local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (socket_ < 0 || bind(socket_, reinterpret_cast<sockaddr *>(&local),
                                sizeof(local)) < 0)
        {
            std::cerr << "[Lite3 UDP] Cannot bind 127.0.0.1:20001: "
                      << std::strerror(errno) << ". Keeping fixed standing."
                      << std::endl;
            if (socket_ >= 0) close(socket_);
            socket_ = -1;
        }
        else
        {
            controller_address_.sin_family = AF_INET;
            controller_address_.sin_port = htons(30010);
            controller_address_.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            std::cout << "[Lite3 UDP] Commands: 127.0.0.1:20001; state: 127.0.0.1:30010"
                      << std::endl;
        }
        ground_truth_publisher_ = transport_.Advertise<gz::msgs::Odometry>(
            "/lite3/ground_truth/odom");
        if (!ground_truth_publisher_)
            std::cerr << "[Lite3 pose] Cannot advertise ground truth." << std::endl;

        transport_.Subscribe("/lite3/control_mode",
                            &Lite3GazeboInterface::OnModeCommand, this);
        std::cout << "[Lite3 control] Mode: stand. Explicit external command required."
                  << std::endl;
    }

    // 物理计算前收取最新指令，然后施加力矩。默认仍为固定站姿。
    void PreUpdate(
        const gz::sim::UpdateInfo &info,
        gz::sim::EntityComponentManager &ecm) override
    {
        if (info.paused || joint_entities_.size() != 12)
        {
            return;
        }

        ReceiveCommands();
        const bool fresh = have_command_ &&
            std::chrono::steady_clock::now() - last_command_ <
                std::chrono::milliseconds(250);
        const int requested = requested_mode_.exchange(-1);
        if (requested == 0) ReturnToStand("requested");
        if (requested == 1)
        {
            bool ready = fresh;
            for (std::size_t i = 0; i < 12; ++i) ready = ready && command_[i] > 0.0f;
            if (ready)
            {
                external_mode_ = true;
                std::cout << "[Lite3 control] Mode: external" << std::endl;
            }
            else std::cerr << "[Lite3 control] External refused: first start controller, "
                           << "stand up, then enter RL." << std::endl;
        }
        if (external_mode_ && !fresh) ReturnToStand("command timeout > 250 ms");

        for (std::size_t i = 0; i < joint_entities_.size(); ++i)
        {
            gz::sim::Joint joint(joint_entities_[i]);
            const auto position = joint.Position(ecm);
            const auto velocity = joint.Velocity(ecm);

            if (!position || position->empty() ||
                !velocity || velocity->empty())
            {
                applied_torque_[i] = 0.0;
                joint.SetForce(ecm, {0.0});
                continue;
            }

            const double angle = position->at(0);
            const double speed = velocity->at(0);

            if (!std::isfinite(angle) || !std::isfinite(speed))
            {
                applied_torque_[i] = 0.0;
                joint.SetForce(ecm, {0.0});
                continue;
            }

            const double target = stand_angles_[i % 3];
            double torque = 30.0 * (target - angle) - 1.0 * speed;
            if (external_mode_)
            {
                torque = command_[i] * (command_[12 + i] - angle) +
                         command_[24 + i] * (command_[36 + i] - speed) +
                         command_[48 + i];
            }

            // 与当前 URDF 的力矩上限一致：髋关节 24，膝关节 36 N·m。
            const double torque_limit = (i % 3 == 2) ? 36.0 : 24.0;
            torque = std::clamp(torque, -torque_limit, torque_limit);
            applied_torque_[i] = torque;
            joint.SetForce(ecm, {torque});
        }
    }

    void PostUpdate(
        const gz::sim::UpdateInfo &info,
        const gz::sim::EntityComponentManager &ecm) override
    {
        if (info.paused)
        {
            return;
        }

        SendState(info, ecm);
        PublishGroundTruth(info, ecm);

        ++print_counter_;
        if (print_counter_ % 1000 != 0)
        {
            return;
        }

        if (body_entity_ != gz::sim::kNullEntity)
        {
            gz::sim::Link body(body_entity_);
            const auto pose = body.WorldPose(ecm);
            const auto world_omega = body.WorldAngularVelocity(ecm);

            if (pose && world_omega)
            {
                const auto rpy = pose->Rot().Euler();
                // 转动速度转换到机身坐标系，和官方 RL 接口保持一致。
                const auto body_omega =
                    pose->Rot().RotateVectorReverse(*world_omega);
                const double rad_to_deg = 180.0 / std::acos(-1.0);

                std::cout
                    << "[Lite3 body] roll_deg=" << rpy.X() * rad_to_deg
                    << " pitch_deg=" << rpy.Y() * rad_to_deg
                    << " yaw_deg=" << rpy.Z() * rad_to_deg
                    << " x_m=" << pose->Pos().X()
                    << " y_m=" << pose->Pos().Y()
                    << " height_m=" << pose->Pos().Z()
                    << std::endl;

                std::cout
                    << "[Lite3 body] omega_body_rad_s="
                    << body_omega.X() << ", "
                    << body_omega.Y() << ", "
                    << body_omega.Z() << std::endl;
            }
            else
            {
                std::cout << "[Lite3 body] State not available yet."
                          << std::endl;
            }
        }

        for (const auto entity : joint_entities_)
        {
            gz::sim::Joint joint(entity);
            const auto position = joint.Position(ecm);
            const auto velocity = joint.Velocity(ecm);

            if (!position || position->empty() ||
                !velocity || velocity->empty())
            {
                continue;
            }

            std::cout
                << "[Lite3 state] "
                << joint.Name(ecm).value_or("unknown")
                << " angle=" << position->at(0)
                << " speed=" << velocity->at(0)
                << std::endl;
        }
    }
};

}  // namespace lite3_control

GZ_ADD_PLUGIN(
    lite3_control::Lite3GazeboInterface,
    gz::sim::System,
    gz::sim::ISystemConfigure,
    gz::sim::ISystemPreUpdate,
    gz::sim::ISystemPostUpdate)

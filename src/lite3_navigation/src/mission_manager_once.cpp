#include <chrono>
#include <cmath>
#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "nav2_msgs/action/compute_path_to_pose.hpp"
#include "nav2_msgs/action/follow_path.hpp"

using namespace std::chrono_literals;
using ComputePath = nav2_msgs::action::ComputePathToPose;
using FollowPath = nav2_msgs::action::FollowPath;

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("mission_manager");

  // 从终端参数读取目标；不需要用户填写起点。
  const double goal_x =
    node->declare_parameter<double>("goal_x", -3.2);
  const double goal_y =
    node->declare_parameter<double>("goal_y", -4.0);
  const double goal_yaw =
    node->declare_parameter<double>("goal_yaw", 0.0);

  auto finish = [](int code) {
      rclcpp::shutdown();
      return code;
    };

  if (!std::isfinite(goal_x) || !std::isfinite(goal_y) ||
    !std::isfinite(goal_yaw))
  {
    RCLCPP_ERROR(node->get_logger(), "目标坐标或朝向不是有效数字");
    return finish(1);
  }

  // 创建客户端，用来向已有的规划器提出任务。
  auto planner = rclcpp_action::create_client<ComputePath>(
    node, "/compute_path_to_pose");

  RCLCPP_INFO(node->get_logger(), "等待规划器，最多等待 5 秒");

  if (!planner->wait_for_action_server(5s)) {
    RCLCPP_ERROR(node->get_logger(), "没有找到规划器，请检查终端 7");
    return finish(1);
  }

  // 填写规划任务。
  ComputePath::Goal request;
  request.goal.header.frame_id = "map";

  // 零时间戳表示使用最新可用变换。
  request.goal.header.stamp.sec = 0;
  request.goal.header.stamp.nanosec = 0;

  request.goal.pose.position.x = goal_x;
  request.goal.pose.position.y = goal_y;
  request.goal.pose.position.z = 0.0;

  // 把朝向角转换成消息要求的表示方式。
  request.goal.pose.orientation.z = std::sin(goal_yaw / 2.0);
  request.goal.pose.orientation.w = std::cos(goal_yaw / 2.0);

  request.planner_id = "GridBased";
  request.use_start = false;

  RCLCPP_INFO(
    node->get_logger(),
    "请求规划：目标 (%.2f, %.2f)，朝向 %.2f rad",
    goal_x, goal_y, goal_yaw);

  // 发送请求，等待规划器确认是否接受。
  auto goal_future = planner->async_send_goal(request);

  if (rclcpp::spin_until_future_complete(node, goal_future) !=
    rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(node->get_logger(), "等待规划器接受请求时被中断");
    return finish(1);
  }

  auto goal_handle = goal_future.get();

  if (!goal_handle) {
    RCLCPP_ERROR(
      node->get_logger(),
      "规划器拒绝了这次请求，请检查是否已启用");
    return finish(1);
  }

  // 任务已接受，再等待真正的规划结果。
  RCLCPP_INFO(node->get_logger(), "规划器已接受请求，等待路线");

  auto result_future = planner->async_get_result(goal_handle);

  if (rclcpp::spin_until_future_complete(node, result_future) !=
    rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(node->get_logger(), "等待规划结果时被中断");
    return finish(1);
  }

  const auto response = result_future.get();

  if (!response.result) {
    RCLCPP_ERROR(node->get_logger(), "规划器没有返回有效结果");
    return finish(1);
  }

  // 接受任务不代表规划成功，还必须检查最终结果。
  if (response.code != rclcpp_action::ResultCode::SUCCEEDED ||
    response.result->error_code != 0)
  {
    RCLCPP_ERROR(
      node->get_logger(),
      "规划未成功：Nav2 错误码 %u，原因：%s",
      static_cast<unsigned>(response.result->error_code),
      response.result->error_msg.c_str());
    return finish(1);
  }

  // 取出规划器返回的完整路线。
  const auto & path = response.result->path;

  if (path.poses.empty() || path.header.frame_id != "map") {
    RCLCPP_ERROR(node->get_logger(), "路线为空，或路线坐标系不是 map");
    return finish(1);
  }

  const auto & start = path.poses.front().pose.position;
  const auto & end = path.poses.back().pose.position;

  RCLCPP_INFO(
    node->get_logger(),
    "获得路线：%zu 个点，起点 (%.2f, %.2f)，终点 (%.2f, %.2f)",
    path.poses.size(), start.x, start.y, end.x, end.y);

  // 创建控制器客户端，使用已有的 /follow_path 接口。
  auto controller = rclcpp_action::create_client<FollowPath>(
    node, "/follow_path");

  RCLCPP_INFO(node->get_logger(), "等待路线跟随控制器，最多等待 5 秒");
  if (!controller->wait_for_action_server(5s)) {
    RCLCPP_ERROR(node->get_logger(), "没有找到控制器，请检查终端 4");
    return finish(1);
  }

  // 将刚才收到的完整路线交给控制器。
  FollowPath::Goal follow_request;
  follow_request.path = path;
  follow_request.controller_id = "FollowPath";
  follow_request.goal_checker_id = "goal_checker";
  follow_request.progress_checker_id = "progress_checker";

  rclcpp_action::Client<FollowPath>::SendGoalOptions options;
  options.feedback_callback = [node](
    rclcpp_action::ClientGoalHandle<FollowPath>::SharedPtr,
    const std::shared_ptr<const FollowPath::Feedback> feedback)
    {
      RCLCPP_INFO_THROTTLE(
        node->get_logger(), *node->get_clock(), 1000,
        "路线跟随反馈：剩余距离 %.2f m，控制器速度 %.2f m/s",
        feedback->distance_to_goal, feedback->speed);
    };

  RCLCPP_INFO(node->get_logger(), "发送路线跟随任务");
  auto follow_goal_future = controller->async_send_goal(
    follow_request, options);

  if (rclcpp::spin_until_future_complete(node, follow_goal_future) !=
    rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(
      node->get_logger(),
      "等待控制器接受任务时被中断；中断本节点不等于取消控制器任务");
    return finish(1);
  }

  auto follow_handle = follow_goal_future.get();
  if (!follow_handle) {
    RCLCPP_ERROR(node->get_logger(), "控制器拒绝了路线跟随任务");
    return finish(1);
  }

  RCLCPP_INFO(node->get_logger(), "控制器已接受路线，等待行走结果");
  auto follow_result_future = controller->async_get_result(follow_handle);

  if (rclcpp::spin_until_future_complete(node, follow_result_future) !=
    rclcpp::FutureReturnCode::SUCCESS)
  {
    RCLCPP_ERROR(
      node->get_logger(),
      "等待行走结果时被中断；如需停止，请锁定运动节点");
    return finish(1);
  }

  const auto follow_response = follow_result_future.get();
  if (!follow_response.result) {
    RCLCPP_ERROR(node->get_logger(), "控制器没有返回有效结果");
    return finish(1);
  }

  // Action 取消状态与 Nav2 错误码是两个不同字段。
  if (follow_response.code == rclcpp_action::ResultCode::CANCELED) {
    RCLCPP_WARN(node->get_logger(), "路线跟随任务已取消");
    return finish(2);
  }

  if (follow_response.code != rclcpp_action::ResultCode::SUCCEEDED ||
    follow_response.result->error_code != 0)
  {
    RCLCPP_ERROR(
      node->get_logger(),
      "路线跟随未成功：Nav2 错误码 %u，原因：%s",
      static_cast<unsigned>(follow_response.result->error_code),
      follow_response.result->error_msg.c_str());
    return finish(1);
  }

  RCLCPP_INFO(node->get_logger(), "控制器报告已到达目标，本次任务结束");

  return finish(0);
}

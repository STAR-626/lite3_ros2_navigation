// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include "keyboard_interface.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

// 仅新增速度输入适配，不创建 ROS2 节点；键盘负责状态切换。
class UdpVelocityInterface : public UserCommandInterface
{
public:
    UdpVelocityInterface() : keyboard_(false)
    {
        socket_ = ::socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
        if (socket_ < 0)
            throw std::runtime_error("Cannot create UDP velocity socket");
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(30011);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (::bind(socket_, reinterpret_cast<const sockaddr *>(&address),
                   sizeof(address)) < 0)
        {
            const std::string reason = std::strerror(errno);
            ::close(socket_);
            socket_ = -1;
            throw std::runtime_error("Cannot bind 127.0.0.1:30011: " + reason);
        }
        std::cout << "[ROS velocity] Listening on 127.0.0.1:30011; "
                  << "12-byte vx/vy/wz packets; timeout 250 ms" << std::endl;
        std::cout << "[ROS velocity] z: stand, c: RL/resume, space: stop latch; "
                  << "movement keys disabled" << std::endl;
    }

    ~UdpVelocityInterface()
    {
        Stop();
        if (socket_ >= 0) ::close(socket_);
    }

    void Start() override { keyboard_.Start(); }
    void Stop() override { keyboard_.Stop(); }

    void SetMotionStateFeedback(const MotionStateFeedback &feedback) override
    {
        // 状态切换后不沿用之前保存的速度，等待新的速度包。
        if (feedback.current_state != current_state_)
        {
            have_velocity_ = false;
            velocity_.fill(0.0f);
        }
        current_state_ = feedback.current_state;
        keyboard_.SetMotionStateFeedback(feedback);
    }

    UserCommand GetUserCommand() override
    {
        const auto now = std::chrono::steady_clock::now();
        const bool discard_backlog = polled_before_ &&
            now - last_poll_ >= std::chrono::milliseconds(250);
        last_poll_ = now;
        polled_before_ = true;
        if (discard_backlog)
        {
            // 仿真暂停或控制循环中断后，丢弃排队的旧速度，等新的数据。
            have_velocity_ = false;
            velocity_.fill(0.0f);
        }
        ReceiveVelocity(discard_backlog);
        UserCommand command = keyboard_.GetUserCommand();
        if (have_velocity_ && std::chrono::steady_clock::now() - last_packet_ >=
                                  std::chrono::milliseconds(250))
        {
            have_velocity_ = false;
            velocity_.fill(0.0f);
            std::cout << "[ROS velocity] Packet timeout; velocity set to zero"
                      << std::endl;
        }

        command.forward_vel_scale = 0.0f;
        command.side_vel_scale = 0.0f;
        command.turnning_vel_scale = 0.0f;
        if (have_velocity_ && !command.soft_stop_flag &&
            current_state_ == int(RobotMotionState::RLControlMode) &&
            command.target_mode == int(RobotMotionState::RLControlMode))
        {
            // 当前策略随后乘以 max_cmd_vel=[0.8,0.8,0.8]。
            command.forward_vel_scale = velocity_[0] / 0.8f;
            command.side_vel_scale = velocity_[1] / 0.8f;
            command.turnning_vel_scale = velocity_[2] / 0.8f;
        }

        const std::array<float, 3> applied{
            command.forward_vel_scale * 0.8f,
            command.side_vel_scale * 0.8f,
            command.turnning_vel_scale * 0.8f};
        if (applied != reported_velocity_)
        {
            std::cout << "[ROS velocity] Policy command vx=" << applied[0]
                      << " vy=" << applied[1] << " wz=" << applied[2]
                      << " (m/s, m/s, rad/s)" << std::endl;
            reported_velocity_ = applied;
        }
        return command;
    }

private:
    void ReceiveVelocity(bool discard_backlog)
    {
        for (int i = 0; i < 256; ++i)
        {
            std::array<float, 3> packet{};
            const auto length = ::recv(
                socket_, packet.data(), sizeof(packet), MSG_DONTWAIT | MSG_TRUNC);
            if (length < 0)
            {
                if (errno != EAGAIN && errno != EWOULDBLOCK)
                {
                    have_velocity_ = false;
                    velocity_.fill(0.0f);
                }
                break;
            }
            if (discard_backlog) continue;
            if (length != static_cast<ssize_t>(sizeof(packet)) ||
                !std::all_of(packet.begin(), packet.end(),
                             [](float value) { return std::isfinite(value); }))
            {
                have_velocity_ = false;
                velocity_.fill(0.0f);
                std::cerr << "[ROS velocity] Invalid packet; velocity set to zero"
                          << std::endl;
                continue;
            }
            for (std::size_t axis = 0; axis < packet.size(); ++axis)
                velocity_[axis] = std::clamp(packet[axis], -0.8f, 0.8f);
            last_packet_ = std::chrono::steady_clock::now();
            have_velocity_ = true;
        }
    }

    KeyboardInterface keyboard_;
    int socket_ = -1;
    int current_state_ = int(RobotMotionState::WaitingForStand);
    bool have_velocity_ = false;
    std::array<float, 3> velocity_{};
    std::array<float, 3> reported_velocity_{};
    std::chrono::steady_clock::time_point last_packet_{};
    std::chrono::steady_clock::time_point last_poll_{};
    bool polled_before_ = false;
};

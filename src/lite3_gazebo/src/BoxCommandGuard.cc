// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// GUI world-axis commands -> native VelocityControl, with a wall-time deadman.
#include <chrono>
#include <cmath>
#include <mutex>
#include <string>
#include <gz/msgs/twist.pb.h>
#include <gz/plugin/RegisterMore.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/Util.hh>
#include <gz/transport/Node.hh>

namespace lite3_gazebo
{
class BoxCommandGuard : public gz::sim::System,
  public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate
{
  using Clock = std::chrono::steady_clock;
public:
  void Configure(const gz::sim::Entity & entity,
    const std::shared_ptr<const sdf::Element> & sdf,
    gz::sim::EntityComponentManager & ecm, gz::sim::EventManager &) override
  {
    link_ = gz::sim::Model(entity).LinkByName(ecm, "box");
    if (link_ == gz::sim::kNullEntity || !sdf->HasElement("topic")) {return;}
    const auto topic = sdf->Get<std::string>("topic");
    publisher_ = transport_.Advertise<gz::msgs::Twist>(topic + "/actuator");
    transport_.Subscribe(topic, &BoxCommandGuard::Command, this);
  }
  void Command(const gz::msgs::Twist & msg)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    x_ = msg.linear().x(); y_ = msg.linear().y();
    const double norm = std::hypot(x_, y_);
    if (!std::isfinite(norm)) {x_ = y_ = 0.;}
    else if (norm > .5) {x_ *= .5/norm; y_ *= .5/norm;}
    received_ = Clock::now();
  }
  void PreUpdate(const gz::sim::UpdateInfo & info,
    gz::sim::EntityComponentManager & ecm) override
  {
    if (link_ == gz::sim::kNullEntity || !publisher_) {return;}
    const auto now = Clock::now();
    if (now - published_ < std::chrono::milliseconds(40)) {return;}
    published_ = now;
    gz::math::Vector3d command;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (!info.paused && now - received_ < std::chrono::milliseconds(300)) {
        command.Set(x_, y_, 0.);
      }
    }
    // Native VelocityControl uses body axes; present consistent world axes to
    // the user even when the physical box has yawed during a collision.
    command = gz::sim::worldPose(link_, ecm).Rot().RotateVectorReverse(command);
    gz::msgs::Twist output;
    output.mutable_linear()->set_x(command.X());
    output.mutable_linear()->set_y(command.Y());
    output.mutable_linear()->set_z(command.Z());
    publisher_.Publish(output);
  }
private:
  gz::sim::Entity link_ = gz::sim::kNullEntity;
  gz::transport::Node transport_;
  gz::transport::Node::Publisher publisher_;
  std::mutex mutex_;
  double x_ = 0., y_ = 0.;
  Clock::time_point received_{}, published_{};
};
}
GZ_ADD_PLUGIN(lite3_gazebo::BoxCommandGuard, gz::sim::System,
  gz::sim::ISystemConfigure, gz::sim::ISystemPreUpdate)
GZ_ADD_PLUGIN_ALIAS(lite3_gazebo::BoxCommandGuard, "lite3_gazebo::BoxCommandGuard")

// SPDX-License-Identifier: BSD-3-Clause
// 动态投放箱子后立即请求Physics的真实接触数据；不修改速度、力或碰撞几何。
#include <chrono>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>
#include <gz/msgs/contacts.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/transport/Node.hh>

namespace lite3_gazebo
{
class BoxContacts : public gz::sim::System,
  public gz::sim::ISystemConfigure, public gz::sim::ISystemPostUpdate
{
public:
  void Configure(const gz::sim::Entity & entity,
    const std::shared_ptr<const sdf::Element> & sdf,
    gz::sim::EntityComponentManager & ecm, gz::sim::EventManager &) override
  {
    const gz::sim::Model model(entity);
    const auto link = model.LinkByName(ecm, "box");
    if (link == gz::sim::kNullEntity) {return;}
    collisions_ = ecm.ChildrenByComponents(link, gz::sim::components::Collision());
    for (auto collision : collisions_) {
      if (!ecm.Component<gz::sim::components::ContactSensorData>(collision)) {
        ecm.CreateComponent(collision, gz::sim::components::ContactSensorData());
      }
    }
    const std::string topic = sdf->HasElement("topic") ?
      sdf->Get<std::string>("topic") : "/lite3/dynamic_box/contacts";
    publisher_ = transport_.Advertise<gz::msgs::Contacts>(topic);
  }

  void PostUpdate(const gz::sim::UpdateInfo & info,
    const gz::sim::EntityComponentManager & ecm) override
  {
    if (info.paused) {return;}
    if (info.simTime < last_) {pending_.clear(); last_ = info.simTime;}
    for (auto collision : collisions_) {
      const auto *data = ecm.Component<gz::sim::components::ContactSensorData>(collision);
      if (!data) {continue;}
      for (const auto & contact : data->Data().contact()) {
        // 每个发布窗口保留每一接触对，避免漏掉短于发布周期的擦碰。
        pending_[{contact.collision1().id(), contact.collision2().id()}] = contact;
      }
    }
    if (info.simTime - last_ < std::chrono::milliseconds(50)) {return;}
    gz::msgs::Contacts message;
    const auto seconds = std::chrono::duration_cast<std::chrono::seconds>(info.simTime);
    auto *stamp = message.mutable_header()->mutable_stamp();
    stamp->set_sec(seconds.count());
    stamp->set_nsec((info.simTime - seconds).count());
    for (const auto & entry : pending_) {*message.add_contact() = entry.second;}
    // 空帧也发布，验收工具可区分“没有接触”和“记录器已退出”。
    publisher_.Publish(message);
    pending_.clear();
    last_ = info.simTime;
  }

private:
  gz::transport::Node transport_;
  gz::transport::Node::Publisher publisher_;
  std::vector<gz::sim::Entity> collisions_;
  std::map<std::pair<uint64_t, uint64_t>, gz::msgs::Contact> pending_;
  std::chrono::nanoseconds last_{0};
};
}  // namespace lite3_gazebo
GZ_ADD_PLUGIN(lite3_gazebo::BoxContacts, gz::sim::System,
  gz::sim::ISystemConfigure, gz::sim::ISystemPostUpdate)
GZ_ADD_PLUGIN_ALIAS(lite3_gazebo::BoxContacts, "lite3_gazebo::BoxContacts")

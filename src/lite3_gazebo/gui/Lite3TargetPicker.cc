// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include "Lite3TargetPicker.hh"

#include <cmath>
#include <chrono>
#include <iostream>
#include <QClipboard>
#include <QGuiApplication>
#include <QUuid>
#include <QQuickWindow>
#include <QKeyEvent>
#include <QEvent>
#include <algorithm>
#include <sstream>
#include <iomanip>
#include <locale>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/entity.pb.h>
#include <gz/msgs/entity_factory.pb.h>
#include <gz/msgs/scene.pb.h>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/twist.pb.h>
#include <gz/gui/Application.hh>
#include <gz/gui/GuiEvents.hh>
#include <gz/gui/MainWindow.hh>
#include <gz/msgs/marker.pb.h>
#include <gz/msgs/pose.pb.h>
#include <gz/plugin/Register.hh>

Lite3TargetPicker::Lite3TargetPicker()
{
  box_name_ = "lite3_gui_box_" + QUuid::createUuid().toString(QUuid::Id128).toStdString();
  box_topic_ = "/lite3/gui_box/" + box_name_ + "/cmd_vel";
  box_timer_.setInterval(50);
  connect(&box_timer_, &QTimer::timeout, this, &Lite3TargetPicker::TickBox);
  timer_.setInterval(500);
  connect(&timer_, &QTimer::timeout, this, &Lite3TargetPicker::PublishSelection);
}

Lite3TargetPicker::~Lite3TargetPicker()
{
  StopBox();
  box_timer_.stop();
  timer_.stop();
  if (selected_) {
    gz::msgs::Marker marker;
    marker.set_ns("lite3_target_picker");
    marker.set_id(1);
    marker.set_action(gz::msgs::Marker::DELETE_MARKER);
    transport_.Request("/marker", marker);
  }
}

void Lite3TargetPicker::LoadConfig(const tinyxml2::XMLElement *config)
{
  if (title.empty()) { title = "Lite3 导航与动态障碍"; }
  if (config) {
    const auto *height = config->FirstChildElement("max_pick_height");
    double value = 0.0;
    if (height && height->QueryDoubleText(&value) == tinyxml2::XML_SUCCESS &&
      std::isfinite(value) && value > 0.0)
    {
      max_height_ = value;
    }
  }
  if (config && config->FirstChildElement("world_name") &&
    config->FirstChildElement("world_name")->GetText()) {
    world_ = config->FirstChildElement("world_name")->GetText();
  }
  box_publisher_ = transport_.Advertise<gz::msgs::Twist>(box_topic_);
  publisher_ = transport_.Advertise<gz::msgs::Pose>("/lite3/selected_goal");
  auto *window = gz::gui::App()->findChild<gz::gui::MainWindow *>();
  if (!window || !publisher_) {
    status_ = QStringLiteral("选点插件初始化失败，请查看 Gazebo 日志。");
    emit Changed();
    return;
  }
  window->installEventFilter(this);
  if (window->QuickWindow()) {window->QuickWindow()->installEventFilter(this);}
  connect(qGuiApp, &QGuiApplication::applicationStateChanged,
    this, [this](Qt::ApplicationState state) {if (state != Qt::ApplicationActive) {StopBox();}});
  box_timer_.start();
  timer_.start();
  std::cout << "[Lite3 picker] Ready; new selections require navigation master switch." << std::endl;
}

QString Lite3TargetPicker::Coordinates() const
{
  if (!selected_) { return QStringLiteral("尚未选择目标"); }
  return QStringLiteral("X：%1 m\nY：%2 m\n地面高度：%3 m")
         .arg(point_.X(), 0, 'f', 3).arg(point_.Y(), 0, 'f', 3).arg(point_.Z(), 0, 'f', 3);
}

void Lite3TargetPicker::Arm()
{
  StopBox();
  box_pick_ = false;
  armed_ = true;
  pending_click_ = false;
  status_ = QStringLiteral("请单击场景地面选点。拖动视角不会选点。");
  emit Changed();
}

void Lite3TargetPicker::CancelPick()
{
  const bool was_box = box_pick_;
  armed_ = false;
  box_pick_ = false;
  pending_click_ = false;
  if (was_box) {box_status_ = QStringLiteral("已取消放置箱子。"); emit BoxChanged();}
  status_ = selected_ ? QStringLiteral("已取消重新选点，保留上次目标。") :
            QStringLiteral("已取消选点。");
  emit Changed();
}

void Lite3TargetPicker::CopyCoordinates()
{
  if (!selected_) { return; }
  QGuiApplication::clipboard()->setText(
    QStringLiteral("x: %1, y: %2").arg(point_.X(), 0, 'f', 3).arg(point_.Y(), 0, 'f', 3));
  status_ = QStringLiteral("坐标已复制；导航反馈请看启动终端或导航状态话题。");
  emit Changed();
}

bool Lite3TargetPicker::eventFilter(QObject *object, QEvent *event)
{
  if (box_control_ && (event->type() == QEvent::KeyPress ||
    event->type() == QEvent::KeyRelease || event->type() == QEvent::ShortcutOverride)) {
    const auto *key = static_cast<QKeyEvent *>(event);
    if (key->modifiers() & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier)) {
      StopBox(); return gz::gui::Plugin::eventFilter(object, event);
    }
    const int code = key->key();
    if (code == Qt::Key_W || code == Qt::Key_S || code == Qt::Key_A ||
      code == Qt::Key_D || code == Qt::Key_Space || code == Qt::Key_Escape)
    {
      event->accept();
      if (event->type() != QEvent::ShortcutOverride && !key->isAutoRepeat()) {
        BoxKey(code, event->type() == QEvent::KeyPress);
      }
      return true;
    }
  }
  if (event->type() == QEvent::WindowDeactivate || event->type() == QEvent::Close) {
    StopBox();
  }
  // Gazebo 先发坐标，再发鼠标释放信息；事件可能来自渲染线程。
  // 先配对两个事件，然后在 GUI 线程更新 QML，避免拖动误选和跨线程写状态。
  if (event->type() == gz::gui::events::LeftClickToScene::kType) {
    const auto point = static_cast<gz::gui::events::LeftClickToScene *>(event)->Point();
    QMetaObject::invokeMethod(this, [this, point]() {
      pending_point_ = point;
      pending_click_ = true;
    }, Qt::QueuedConnection);
  } else if (event->type() == gz::gui::events::LeftClickOnScene::kType) {
    const bool dragging =
      static_cast<gz::gui::events::LeftClickOnScene *>(event)->Mouse().Dragging();
    QMetaObject::invokeMethod(this, [this, dragging]() {
      const bool paired = pending_click_;
      pending_click_ = false;
      if (paired && armed_ && !dragging) { ChoosePoint(pending_point_); }
    }, Qt::QueuedConnection);
  }
  // 保留其他插件的选择、视角移动等行为。
  return gz::gui::Plugin::eventFilter(object, event);
}

void Lite3TargetPicker::ChoosePoint(const gz::math::Vector3d &point)
{
  if (!point.IsFinite() || std::abs(point.X()) > 1000.0 || std::abs(point.Y()) > 1000.0 ||
    point.Z() < -0.02 || point.Z() > max_height_)
  {
    status_ = QStringLiteral("请选择地面，货架顶部或天空不能作为本阶段目标。");
    if (box_pick_) {box_status_ = status_; emit BoxChanged();}
    emit Changed();
    return;
  }
  if (box_pick_) {
    armed_ = box_pick_ = false;
    SpawnBox(point);
    emit Changed();
    return;
  }
  point_ = point;
  selected_ = true;
  armed_ = false;
  selected_at_ns_ = std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::system_clock::now().time_since_epoch()).count();
  status_ = QStringLiteral("已发送新选点。总开关开启且空闲时会立即导航；结果请看启动终端。");
  PublishSelection();
  std::cout << "[Lite3 picker] Selected x=" << point_.X() << " y=" << point_.Y()
            << " z=" << point_.Z() << "; new click published." << std::endl;
  emit Changed();
}

void Lite3TargetPicker::PublishSelection()
{
  if (!selected_) { return; }
  gz::msgs::Pose pose;
  // 点击的系统时间是命令去重标识，每次重发保持相同，不能使用不断变化的仿真时钟。
  pose.mutable_header()->mutable_stamp()->set_sec(selected_at_ns_ / 1000000000LL);
  pose.mutable_header()->mutable_stamp()->set_nsec(selected_at_ns_ % 1000000000LL);
  // 本项目当前 world、map、odom 原点和轴一致；未来引入定位时要转换坐标。
  auto *frame = pose.mutable_header()->add_data();
  frame->set_key("frame_id");
  frame->add_value("map");
  pose.mutable_position()->set_x(point_.X());
  pose.mutable_position()->set_y(point_.Y());
  pose.mutable_position()->set_z(point_.Z());
  pose.mutable_orientation()->set_w(1.0);
  publisher_.Publish(pose);

  // MarkerManager 只创建 GUI 标记，没有 Gazebo 碰撞体或导航障碍物。
  gz::msgs::Marker marker;
  marker.set_ns("lite3_target_picker");
  marker.set_id(1);
  marker.set_action(gz::msgs::Marker::ADD_MODIFY);
  marker.set_type(gz::msgs::Marker::SPHERE);
  marker.set_visibility(gz::msgs::Marker::GUI);
  *marker.mutable_pose() = pose;
  marker.mutable_pose()->mutable_position()->set_z(point_.Z() + 0.035);
  marker.mutable_scale()->set_x(0.30);
  marker.mutable_scale()->set_y(0.30);
  marker.mutable_scale()->set_z(0.05);
  auto *color = marker.mutable_material()->mutable_diffuse();
  color->set_r(1.0); color->set_g(0.35); color->set_b(0.0); color->set_a(1.0);
  *marker.mutable_material()->mutable_ambient() = *color;
  transport_.Request("/marker", marker);
}



void Lite3TargetPicker::ArmBox(double length, double width, double height, double speed)
{
  StopBox();
  armed_ = box_pick_ = pending_click_ = false;
  emit Changed();
  auto valid = [](double value) {return std::isfinite(value) && value >= .1 && value <= 2.;};
  if (!valid(length) || !valid(width) || !valid(height) ||
    !std::isfinite(speed) || speed < .05 || speed > .5)
  {
    box_status_ = QStringLiteral("尺寸需为0.10～2.00米，速度需为0.05～0.50米/秒。");
  } else if (has_box_ || box_busy_ || uncertain_) {
    box_status_ = QStringLiteral("先移除当前箱子；状态不确定时请先检查箱子状态。");
  } else {
    box_length_ = length; box_width_ = width; box_height_ = height; box_speed_ = speed;
    armed_ = box_pick_ = true; pending_click_ = false;
    box_status_ = QStringLiteral("请点击空旷地面放置箱子；不要与机器狗或货架重叠。");
    emit Changed();
  }
  emit BoxChanged();
}

void Lite3TargetPicker::SetBoxSpeed(double speed)
{
  if (std::isfinite(speed) && speed >= .05 && speed <= .5) {box_speed_ = speed;}
  else {StopBox(); box_status_ = QStringLiteral("速度需为0.05～0.50米/秒。"); emit BoxChanged();}
}

void Lite3TargetPicker::SetBoxControl(bool enabled)
{
  if (!enabled) {StopBox(); return;}
  if (!HasBox() || box_busy_) {box_status_ = QStringLiteral("请先放置并确认箱子。"); emit BoxChanged(); return;}
  armed_ = box_pick_ = pending_click_ = false;
  held_.clear(); box_control_ = true;
  box_status_ = QStringLiteral("控制区已启用：W/S沿世界±X，A/D沿世界±Y；松键停止，空格停车。");
  emit Changed(); emit BoxChanged(); emit BoxControlChanged();
}

void Lite3TargetPicker::BoxKey(int key, bool pressed)
{
  if (!box_control_ || !HasBox() || box_busy_) {return;}
  if (key == Qt::Key_Space || key == Qt::Key_Escape) {StopBox(); return;}
  if (key != Qt::Key_W && key != Qt::Key_S && key != Qt::Key_A && key != Qt::Key_D) {return;}
  if (pressed) {held_.insert(key);} else {held_.erase(key);}
  PublishBoxVelocity();
}

void Lite3TargetPicker::StopBox()
{
  const bool was_enabled = box_control_;
  box_control_ = false; held_.clear(); PublishBoxVelocity();
  if (was_enabled) {
    box_status_ = QStringLiteral("箱子控制已停止。再次点击启用后才能移动。");
    emit BoxChanged(); emit BoxControlChanged();
  }
}

void Lite3TargetPicker::PublishBoxVelocity()
{
  if (!box_publisher_) {return;}
  gz::msgs::Twist message;
  if (box_control_ && HasBox() && !box_busy_) {
    double x = static_cast<int>(held_.count(Qt::Key_W)) - static_cast<int>(held_.count(Qt::Key_S));
    double y = static_cast<int>(held_.count(Qt::Key_A)) - static_cast<int>(held_.count(Qt::Key_D));
    const double norm = std::hypot(x, y);
    if (norm > 0.) {x *= box_speed_/norm; y *= box_speed_/norm;}
    message.mutable_linear()->set_x(x); message.mutable_linear()->set_y(y);
  }
  box_publisher_.Publish(message);
}

void Lite3TargetPicker::SpawnBox(const gz::math::Vector3d & point)
{
  if (has_box_ || box_busy_ || uncertain_) {return;}
  const double mass = 5.;
  const double x2 = box_length_*box_length_, y2 = box_width_*box_width_, z2 = box_height_*box_height_;
  std::ostringstream xml; xml.imbue(std::locale::classic()); xml << std::setprecision(12);
  xml << "<sdf version='1.8'><model name='" << box_name_ << "'><static>false</static><pose>"
      << point.X() << ' ' << point.Y() << ' ' << point.Z()+box_height_/2.+.003
      << " 0 0 0</pose><link name='box'><inertial><mass>5</mass><inertia><ixx>"
      << mass*(y2+z2)/12. << "</ixx><iyy>" << mass*(x2+z2)/12. << "</iyy><izz>"
      << mass*(x2+y2)/12. << "</izz></inertia></inertial>";
  for (const auto & tag : {"collision", "visual"}) {
    xml << '<' << tag << " name='" << tag << "'><geometry><box><size>"
        << box_length_ << ' ' << box_width_ << ' ' << box_height_ << "</size></box></geometry>";
    if (std::string(tag) == "visual") {
      xml << "<material><ambient>0.95 0.3 0.05 1</ambient><diffuse>0.95 0.3 0.05 1</diffuse></material>";
    }
    xml << "</" << tag << '>';
  }
  xml << "</link><plugin filename='libLite3BoxContacts.so' name='lite3_gazebo::BoxCommandGuard'><topic>"
      << box_topic_ << "</topic></plugin><plugin filename='gz-sim-velocity-control-system' "
      << "name='gz::sim::systems::VelocityControl'><topic>" << box_topic_
      << "/actuator</topic></plugin>"
      << "<plugin filename='gz-sim-pose-publisher-system' name='gz::sim::systems::PosePublisher'>"
      << "<publish_model_pose>true</publish_model_pose><publish_link_pose>false</publish_link_pose>"
      << "<publish_nested_model_pose>false</publish_nested_model_pose><use_pose_vector_msg>false</use_pose_vector_msg>"
      << "<update_frequency>20</update_frequency><topic>" << box_topic_ << "/pose</topic></plugin>"
      << "<plugin filename='libLite3BoxContacts.so' name='lite3_gazebo::BoxContacts'><topic>"
      << box_topic_ << "/contacts</topic></plugin></model></sdf>";
  gz::msgs::EntityFactory request; request.set_sdf(xml.str()); request.set_allow_renaming(false);
  operation_ = "spawn"; box_busy_ = true; deadline_ = Clock::now()+std::chrono::seconds(8);
  auto reply = std::make_shared<Reply>(); reply->kind = "create"; reply_ = reply;
  std::function<void(const gz::msgs::Boolean &, bool)> callback =
    [reply](const gz::msgs::Boolean & value, bool ok) {
      std::lock_guard<std::mutex> lock(reply->mutex); reply->ok = ok && value.data(); reply->done = true;
    };
  if (!transport_.Request("/world/"+world_+"/create", request, callback)) {
    std::lock_guard<std::mutex> lock(reply->mutex); reply->done = true;
  }
  box_status_ = QStringLiteral("正在创建箱子并核实场景，请稍候…"); emit BoxChanged();
}

void Lite3TargetPicker::RemoveBox()
{
  StopBox();
  if (box_busy_ || (!has_box_ && !uncertain_)) {return;}
  operation_ = "remove"; box_busy_ = true; deadline_ = Clock::now()+std::chrono::seconds(8);
  gz::msgs::Entity request; request.set_name(box_name_); request.set_type(gz::msgs::Entity::MODEL);
  auto reply = std::make_shared<Reply>(); reply->kind = "remove"; reply_ = reply;
  std::function<void(const gz::msgs::Boolean &, bool)> callback =
    [reply](const gz::msgs::Boolean & value, bool ok) {
      std::lock_guard<std::mutex> lock(reply->mutex); reply->ok = ok && value.data(); reply->done = true;
    };
  if (!transport_.Request("/world/"+world_+"/remove", request, callback)) {
    std::lock_guard<std::mutex> lock(reply->mutex); reply->done = true;
  }
  box_status_ = QStringLiteral("正在移除本面板创建的箱子…"); emit BoxChanged();
}

void Lite3TargetPicker::RefreshBox()
{
  StopBox();
  if (box_busy_) {return;}
  operation_ = "refresh"; box_busy_ = true; deadline_ = Clock::now()+std::chrono::seconds(8);
  reply_.reset(); next_query_ = Clock::now();
  box_status_ = QStringLiteral("正在检查箱子是否仍在场景中…"); emit BoxChanged();
}

void Lite3TargetPicker::QueryBox()
{
  auto reply = std::make_shared<Reply>(); reply->kind = "scene"; reply_ = reply;
  const auto name = box_name_;
  std::function<void(const gz::msgs::Scene &, bool)> callback =
    [reply, name](const gz::msgs::Scene & scene, bool ok) {
      bool exists = false;
      for (const auto & model : scene.model()) {if (model.name() == name) {exists = true;}}
      std::lock_guard<std::mutex> lock(reply->mutex);
      reply->ok = ok; reply->exists = exists; reply->done = true;
    };
  gz::msgs::Empty request;
  if (!transport_.Request("/world/"+world_+"/scene/info", request, callback)) {
    std::lock_guard<std::mutex> lock(reply->mutex); reply->done = true;
  }
}

void Lite3TargetPicker::TickBox()
{
  if (box_control_) {PublishBoxVelocity();}
  if (!box_busy_) {return;}
  if (Clock::now() > deadline_) {
    box_busy_ = false; uncertain_ = true; reply_.reset(); StopBox();
    box_status_ = QStringLiteral("场景确认超时，禁止控制。请检查仿真后点击检查状态；不要重复放置。");
    emit BoxChanged(); return;
  }
  if (reply_) {
    bool done, ok, exists; std::string kind;
    {
      std::lock_guard<std::mutex> lock(reply_->mutex);
      done = reply_->done; ok = reply_->ok; exists = reply_->exists; kind = reply_->kind;
    }
    if (!done) {return;}
    reply_.reset();
    if (kind == "scene" && ok && (operation_ == "refresh" ||
      (operation_ == "spawn" && exists) || (operation_ == "remove" && !exists)))
    {
      has_box_ = exists; uncertain_ = box_busy_ = false;
      box_status_ = exists ? QStringLiteral("箱子已确认。启用控制区后使用WASD或方向按钮。") :
        QStringLiteral("本面板箱子已移除或不存在，可以重新放置。");
      emit BoxChanged(); return;
    }
    next_query_ = Clock::now()+std::chrono::milliseconds(200);
  }
  if (Clock::now() >= next_query_) {QueryBox();}
}

GZ_ADD_PLUGIN(Lite3TargetPicker, gz::gui::Plugin)

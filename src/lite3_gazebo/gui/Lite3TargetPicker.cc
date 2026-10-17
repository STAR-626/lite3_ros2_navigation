// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include "Lite3TargetPicker.hh"

#include <cmath>
#include <chrono>
#include <iostream>
#include <QClipboard>
#include <QGuiApplication>
#include <gz/gui/Application.hh>
#include <gz/gui/GuiEvents.hh>
#include <gz/gui/MainWindow.hh>
#include <gz/msgs/marker.pb.h>
#include <gz/msgs/pose.pb.h>
#include <gz/plugin/Register.hh>

Lite3TargetPicker::Lite3TargetPicker()
{
  timer_.setInterval(500);
  connect(&timer_, &QTimer::timeout, this, &Lite3TargetPicker::PublishSelection);
}

Lite3TargetPicker::~Lite3TargetPicker()
{
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
  if (title.empty()) { title = "Lite3 目标选点"; }
  if (config) {
    const auto *height = config->FirstChildElement("max_pick_height");
    double value = 0.0;
    if (height && height->QueryDoubleText(&value) == tinyxml2::XML_SUCCESS &&
      std::isfinite(value) && value > 0.0)
    {
      max_height_ = value;
    }
  }
  publisher_ = transport_.Advertise<gz::msgs::Pose>("/lite3/selected_goal");
  auto *window = gz::gui::App()->findChild<gz::gui::MainWindow *>();
  if (!window || !publisher_) {
    status_ = QStringLiteral("选点插件初始化失败，请查看 Gazebo 日志。");
    emit Changed();
    return;
  }
  window->installEventFilter(this);
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
  armed_ = true;
  pending_click_ = false;
  status_ = QStringLiteral("请单击场景地面选点。拖动视角不会选点。");
  emit Changed();
}

void Lite3TargetPicker::CancelPick()
{
  armed_ = false;
  pending_click_ = false;
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

GZ_ADD_PLUGIN(Lite3TargetPicker, gz::gui::Plugin)

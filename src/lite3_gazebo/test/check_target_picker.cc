// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// Loads the actual QML plugin; scene events stand in for Gazebo's ray picking.
#include <QClipboard>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QKeyEvent>
#include <gz/msgs/twist.pb.h>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/entity.pb.h>
#include <gz/msgs/entity_factory.pb.h>
#include <gz/msgs/scene.pb.h>
#include <gz/msgs/empty.pb.h>
#include <QQmlApplicationEngine>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQuickWindow>
#include <QThread>
#include <gz/common/MouseEvent.hh>
#include <gz/gui/Application.hh>
#include <gz/gui/GuiEvents.hh>
#include <gz/gui/MainWindow.hh>
#include <gz/gui/Plugin.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/marker.pb.h>
#include <gz/msgs/pose.pb.h>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <vector>
#include <unistd.h>

void Check(bool value, const char *message)
{
  if (!value) { throw std::runtime_error(message); }
}

void Pump(int milliseconds)
{
  QElapsedTimer elapsed;
  elapsed.start();
  do {
    QCoreApplication::processEvents();
    QThread::msleep(5);
  } while (elapsed.elapsed() < milliseconds);
}

int main(int argc, char **argv)
{
  if (!qEnvironmentVariableIsSet("GZ_PARTITION")) {
    qputenv("GZ_PARTITION", QByteArray("lite3-picker-test-") + QByteArray::number(getpid()));
  }
  try {
    std::mutex mutex;
    std::vector<gz::msgs::Marker> markers;
    std::vector<gz::msgs::Pose> poses;
    std::vector<gz::msgs::Twist> velocities;
    bool box_exists = false;
    std::string owned_name, created_sdf;
    int create_count = 0, remove_count = 0, scene_count = 0;
    gz::transport::Node probe;
    std::function<bool(const gz::msgs::EntityFactory &, gz::msgs::Boolean &)> create_box =
      [&](const gz::msgs::EntityFactory & req, gz::msgs::Boolean & rep) {
        std::lock_guard<std::mutex> lock(mutex); created_sdf = req.sdf();
        box_exists = true; ++create_count; scene_count = 0; rep.set_data(true); return true;
      };
    std::function<bool(const gz::msgs::Entity &, gz::msgs::Boolean &)> remove_box =
      [&](const gz::msgs::Entity & req, gz::msgs::Boolean & rep) {
        std::lock_guard<std::mutex> lock(mutex);
        const bool own = req.name() == owned_name && req.type() == gz::msgs::Entity::MODEL;
        if (own) {box_exists = false; ++remove_count;} rep.set_data(own); return true;
      };
    std::function<bool(const gz::msgs::Empty &, gz::msgs::Scene &)> scene =
      [&](const gz::msgs::Empty &, gz::msgs::Scene & rep) {
        std::lock_guard<std::mutex> lock(mutex); ++scene_count;
        if (box_exists && scene_count > 2) {rep.add_model()->set_name(owned_name);}
        return true;
      };
    Check(probe.Advertise("/world/large_warehouse/create", create_box), "mock create service");
    Check(probe.Advertise("/world/large_warehouse/remove", remove_box), "mock remove service");
    Check(probe.Advertise("/world/large_warehouse/scene/info", scene), "mock scene verification");
    std::function<void(const gz::msgs::Marker &)> record_marker =
      [&](const gz::msgs::Marker &marker) {
        std::lock_guard<std::mutex> lock(mutex);
        markers.push_back(marker);
      };
    Check(probe.Advertise("/marker", record_marker), "marker service");
    gz::gui::Application app(argc, argv);
    QString plugin_name;
    QObject::connect(&app, &gz::gui::Application::PluginAdded,
      [&](const QString &name) { plugin_name = name; });
    Check(app.LoadPlugin("Lite3TargetPicker"), "load compiled plugin and QML");
    Pump(200);
    auto plugin = app.PluginByName(plugin_name.toStdString());
    Check(static_cast<bool>(plugin), "resolve loaded picker");
    auto armed = [&]() { return plugin->property("armed").toBool(); };
    auto selected_goal = [&]() { return plugin->property("hasSelection").toBool(); };
    auto coordinates = [&]() { return plugin->property("coordinates").toString(); };
    auto *window = app.findChild<gz::gui::MainWindow *>();
    Check(window != nullptr, "Gazebo main window");
    auto click = [&](double x, double y, double z, bool dragging = false) {
      gz::gui::events::LeftClickToScene point({x, y, z});
      gz::common::MouseEvent mouse;
      mouse.SetType(gz::common::MouseEvent::RELEASE);
      mouse.SetButton(gz::common::MouseEvent::LEFT);
      mouse.SetDragging(dragging);
      gz::gui::events::LeftClickOnScene release(mouse);
      QCoreApplication::sendEvent(window, &point);
      QCoreApplication::sendEvent(window, &release);
      Pump(50);
    };
    click(1, 2, 0);
    Check(!selected_goal(), "ordinary clicks must not choose");
    QQuickWindow *quick_window = window->QuickWindow();
    Check(quick_window != nullptr, "QML window loaded");
    quick_window->resize(650, 550);
    quick_window->show();
    Pump(200);
    auto *button = plugin->PluginItem()->findChild<QObject *>("armButton");
    Check(button != nullptr, "actual QML arm button");
    Check(QMetaObject::invokeMethod(button, "clicked"), "QML button callback");
    Check(armed(), "QML button arms picker");
    click(1, 2, 0, true);
    Check(armed() && !selected_goal(), "drag must not choose");
    click(1, 2, 1.0);
    Check(armed() && !selected_goal(), "reject shelf top");
    click(std::numeric_limits<double>::quiet_NaN(), 2, 0);
    Check(armed() && !selected_goal(), "reject NaN");
    click(-2.5, 3.25, 0);
    Check(selected_goal() && !armed(), "accept ground once");
    const auto selected = coordinates();
    Check(selected.contains("-2.500") && selected.contains("3.250"), "coordinates");
    click(5, 5, 0);
    Check(coordinates() == selected, "ordinary click preserves chosen target");
    Check(QMetaObject::invokeMethod(plugin.get(), "Arm"), "arm again");
    Check(QMetaObject::invokeMethod(plugin.get(), "CancelPick"), "cancel picking");
    Check(!armed() && coordinates() == selected, "cancel preserves target");
    Check(QMetaObject::invokeMethod(plugin.get(), "CopyCoordinates"), "copy coordinates");
    Check(QGuiApplication::clipboard()->text() == "x: -2.500, y: 3.250", "clipboard");
    // Subscribe after choosing: the timer must make the latest choice available.
    std::function<void(const gz::msgs::Pose &)> record_pose =
      [&](const gz::msgs::Pose &pose) {
        std::lock_guard<std::mutex> lock(mutex);
        poses.push_back(pose);
      };
    Check(probe.Subscribe("/lite3/selected_goal", record_pose), "late subscriber");
    Pump(1500);
    {
      std::lock_guard<std::mutex> lock(mutex);
      Check(!poses.empty(), "periodic selected-goal publication");
      const auto &pose = poses.back();
      Check(pose.position().x() == -2.5 && pose.position().y() == 3.25, "pose position");
      Check(pose.header().data(0).key() == "frame_id" &&
        pose.header().data(0).value(0) == "map", "map frame");
      Check(!markers.empty(), "marker service receives request");
      const auto &marker = markers.back();
      Check(marker.ns() == "lite3_target_picker" && marker.id() == 1 &&
        marker.visibility() == gz::msgs::Marker::GUI &&
        marker.action() == gz::msgs::Marker::ADD_MODIFY, "GUI-only marker");
      Check(std::abs(marker.pose().position().z() - 0.035) < 1e-9, "marker height");
    }
    // Same real plugin and QML, with asynchronous scene services standing in
    // for Gazebo. Confirmed scene presence, not create's queued acknowledgement.
    auto wait = [&](const std::function<bool()> & pred) {
      for (int i = 0; i < 100 && !pred(); ++i) {Pump(30);}
      Check(pred(), "wait for GUI state or command");
    };
    auto invoke_box = [&](double length, double width, double height, double speed) {
      Check(QMetaObject::invokeMethod(plugin.get(), "ArmBox", Q_ARG(double, length),
        Q_ARG(double, width), Q_ARG(double, height), Q_ARG(double, speed)), "ArmBox invocation");
    };
    auto control = [&]() {return plugin->property("boxControl").toBool();};
    auto has_box = [&]() {return plugin->property("hasBox").toBool();};
    owned_name = plugin->property("boxName").toString().toStdString();
    std::function<void(const gz::msgs::Twist &)> record_velocity =
      [&](const gz::msgs::Twist & msg) {std::lock_guard<std::mutex> lock(mutex); velocities.push_back(msg);};
    Check(probe.Subscribe("/lite3/gui_box/"+owned_name+"/cmd_vel", record_velocity), "box-only velocity topic");
    auto last_velocity = [&]() {
      std::lock_guard<std::mutex> lock(mutex);
      return velocities.empty() ? gz::msgs::Twist() : velocities.back();
    };
    auto *tabs = plugin->PluginItem()->findChild<QObject *>("modeTabs");
    Check(tabs != nullptr, "two-mode tabs"); tabs->setProperty("currentIndex", 1); Pump(60);
    invoke_box(.0, .4, .4, .15); Check(!armed(), "invalid box dimensions cannot arm scene picking");
    invoke_box(.4, .3, .2, .15); Check(armed(), "box placement arms ground picker");
    click(2., -1., .005); Check(!armed() && !has_box(), "queued create not treated as scene confirmation");
    wait(has_box); Check(coordinates() == selected, "box placement never changes navigation goal");
    {
      std::lock_guard<std::mutex> lock(mutex);
      Check(create_count == 1 && created_sdf.find("0.4 0.3 0.2") != std::string::npos,
        "configured size in collision and visual geometry");
      Check(created_sdf.find("BoxCommandGuard") != std::string::npos, "server-side deadman in spawned model");
    }
    auto *control_button = plugin->PluginItem()->findChild<QObject *>("boxControlButton");
    Check(control_button != nullptr, "real QML control button");
    auto enable = [&]() {
      quick_window->requestActivate(); Pump(40);
      Check(QMetaObject::invokeMethod(control_button, "clicked"), "enable control from QML");
      Pump(40); Check(control(), "keyboard control enabled with focus");
    };
    auto key = [&](int code, bool pressed, bool repeat = false) {
      QKeyEvent event(pressed ? QEvent::KeyPress : QEvent::KeyRelease,
        code, Qt::NoModifier, QString(), repeat);
      QCoreApplication::sendEvent(quick_window, &event); Pump(60);
    };
    enable(); key(Qt::Key_W, true);
    wait([&]() {return last_velocity().linear().x() > .14;});
    key(Qt::Key_W, false, true); Check(last_velocity().linear().x() > .14, "auto-repeat release ignored");
    key(Qt::Key_D, true);
    Check(std::abs(std::hypot(last_velocity().linear().x(), last_velocity().linear().y())-.15) < .001,
      "diagonal speed remains bounded");
    key(Qt::Key_W, false); Check(last_velocity().linear().y() < -.14, "remaining key continues motion");
    key(Qt::Key_D, false); Check(last_velocity().linear().x() == 0. && last_velocity().linear().y() == 0., "key release stops");
    key(Qt::Key_W, true); key(Qt::Key_Space, true); Check(!control(), "space stops and disarms control");
    enable(); key(Qt::Key_A, true);
    QEvent deactivate(QEvent::WindowDeactivate); QCoreApplication::sendEvent(quick_window, &deactivate); Pump(60);
    Check(!control() && last_velocity().linear().y() == 0., "window deactivation stops");
    enable(); key(Qt::Key_W, true); tabs->setProperty("currentIndex", 0); Pump(60);
    Check(!control() && last_velocity().linear().x() == 0., "switching to navigation stops box");
    tabs->setProperty("currentIndex", 1); Pump(30);
    Check(QMetaObject::invokeMethod(plugin.get(), "RemoveBox"), "remove box"); wait([&]() {return !has_box() && !plugin->property("boxBusy").toBool();});
    {std::lock_guard<std::mutex> lock(mutex); Check(remove_count == 1, "remove only owned model");}
    invoke_box(.4, .4, .4, .15); click(2., -1., .005); wait(has_box);
    enable(); key(Qt::Key_W, true);
    if (argc > 1) {
      auto *item = plugin->PluginItem();
      item->setWidth(370);
      item->setHeight(640);
      Pump(100);
      const auto capture = item->grabToImage();
      Check(static_cast<bool>(capture), "request QML preview");
      Pump(500);
      Check(capture->image().save(argv[1]), "save QML preview");
    }
    Check(app.RemovePlugin(plugin_name.toStdString()), "remove own plugin");
    plugin.reset();
    Pump(400);
    Check(last_velocity().linear().x() == 0., "plugin close sends box stop");
    {
      std::lock_guard<std::mutex> lock(mutex);
      Check(markers.back().action() == gz::msgs::Marker::DELETE_MARKER,
        "delete only own marker on exit");
    }
    std::cout << "PASS: real plugin/QML, scene-event pairing, filtering, clipboard, "
              << "transport, dual-mode box lifecycle, WASD/focus stop and cleanup. No robot navigation sent." << std::endl;
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "FAIL: " << error.what() << std::endl;
    return 1;
  }
}

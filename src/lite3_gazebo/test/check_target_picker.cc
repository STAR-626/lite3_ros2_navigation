// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// Loads the actual QML plugin; scene events stand in for Gazebo's ray picking.
#include <QClipboard>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QGuiApplication>
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
    gz::transport::Node probe;
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
    if (argc > 1) {
      auto *item = plugin->PluginItem();
      item->setWidth(330);
      item->setHeight(410);
      Pump(100);
      const auto capture = item->grabToImage();
      Check(static_cast<bool>(capture), "request QML preview");
      Pump(500);
      Check(capture->image().save(argv[1]), "save QML preview");
    }
    Check(app.RemovePlugin(plugin_name.toStdString()), "remove own plugin");
    plugin.reset();
    Pump(400);
    {
      std::lock_guard<std::mutex> lock(mutex);
      Check(markers.back().action() == gz::msgs::Marker::DELETE_MARKER,
        "delete only own marker on exit");
    }
    std::cout << "PASS: real plugin/QML, scene-event pairing, filtering, clipboard, "
              << "transport, GUI marker and cleanup. No navigation sent." << std::endl;
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "FAIL: " << error.what() << std::endl;
    return 1;
  }
}

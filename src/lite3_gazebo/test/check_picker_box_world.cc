// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// Actual QML plugin + physics world. No ROS, robot or RL process.
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QProcess>
#include <QQuickWindow>
#include <QQuickItem>
#include <QThread>
#include <gz/gui/Application.hh>
#include <gz/gui/MainWindow.hh>
#include <gz/gui/GuiEvents.hh>
#include <gz/gui/Plugin.hh>
#include <gz/common/MouseEvent.hh>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/pose.pb.h>
#include <gz/msgs/contacts.pb.h>
#include <gz/msgs/scene.pb.h>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/twist.pb.h>
#include <gz/transport/Node.hh>
#include <cmath>
#include <functional>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <unistd.h>

void Check(bool value, const char *why) {if (!value) {throw std::runtime_error(why);}}
void Pump(int ms) {
  QElapsedTimer t; t.start();
  do {QCoreApplication::processEvents(); QThread::msleep(5);} while (t.elapsed() < ms);
}
int main(int argc, char **argv)
{
  if (argc < 2) {return 2;}
  qputenv("GZ_PARTITION", QByteArray("lite3-picker-physics-")+QByteArray::number(getpid()));
  QProcess server;
  try {
    server.setProcessChannelMode(QProcess::MergedChannels);
    server.setStandardOutputFile("/tmp/lite3-picker-physics-"+QString::number(getpid())+".log");
    server.start("gz", {"sim", "-s", "-r", argv[1]});
    Check(server.waitForStarted(3000), "start isolated physics world");
    gz::transport::Node probe;
    gz::gui::Application app(argc, argv);
    QString plugin_name;
    QObject::connect(&app, &gz::gui::Application::PluginAdded,
      [&](const QString &name) {plugin_name = name;});
    Check(app.LoadPlugin("Lite3TargetPicker"), "load GUI plugin"); Pump(200);
    auto plugin = app.PluginByName(plugin_name.toStdString()); Check(bool(plugin), "get plugin");
    auto wait = [&](const std::function<bool()> &pred) {
      for (int i=0; i<200 && !pred(); ++i) {Pump(25);}
      Check(pred(), "wait for native model, transport or GUI confirmation");
    };
    auto *window = app.findChild<gz::gui::MainWindow *>(); Check(window, "GUI window");
    auto *quick = window->QuickWindow(); quick->show(); quick->requestActivate(); Pump(100);
    auto *tabs = plugin->PluginItem()->findChild<QObject *>("modeTabs"); Check(tabs, "mode tabs"); tabs->setProperty("currentIndex", 1);
    const auto name = plugin->property("boxName").toString().toStdString();
    const auto topic = "/lite3/gui_box/"+name+"/cmd_vel";
    std::mutex mutex; gz::msgs::Pose pose; int poses=0, contacts=0;
    std::function<void(const gz::msgs::Pose &)> on_pose = [&](const gz::msgs::Pose &p) {
      std::lock_guard<std::mutex> l(mutex); pose=p; ++poses;
    };
    std::function<void(const gz::msgs::Contacts &)> on_contacts = [&](const gz::msgs::Contacts &m) {
      std::lock_guard<std::mutex> l(mutex);
      for (const auto &c:m.contact()) {
        if (c.collision1().name().find("fixture_wall") != std::string::npos ||
          c.collision2().name().find("fixture_wall") != std::string::npos) {++contacts;}
      }
    };
    Check(probe.Subscribe(topic+"/pose", on_pose), "model pose publisher");
    Check(probe.Subscribe(topic+"/contacts", on_contacts), "real collision publisher");
    auto position = [&]() {std::lock_guard<std::mutex> l(mutex); return pose.position();};
    Check(QMetaObject::invokeMethod(plugin.get(), "ArmBox", Q_ARG(double,.4), Q_ARG(double,.3),
      Q_ARG(double,.2), Q_ARG(double,.5)), "place configured box");
    gz::gui::events::LeftClickToScene point({1.,1.,.005});
    gz::common::MouseEvent mouse; mouse.SetType(gz::common::MouseEvent::RELEASE); mouse.SetButton(gz::common::MouseEvent::LEFT); mouse.SetDragging(false);
    gz::gui::events::LeftClickOnScene click(mouse);
    QCoreApplication::sendEvent(window,&point); QCoreApplication::sendEvent(window,&click);
    wait([&]() {std::lock_guard<std::mutex> l(mutex); return plugin->property("hasBox").toBool() && poses>0;});
    Check(std::abs(position().z()-.108)<.025, "configured height rests near selected ground");
    auto enable = [&]() {
      quick->requestActivate(); Pump(40);
      Check(QMetaObject::invokeMethod(plugin.get(), "SetBoxControl", Q_ARG(bool,true)), "enable box control");
      Check(plugin->property("boxControl").toBool(), "box mode active");
    };
    auto key = [&](int code,bool pressed) {
      Check(QMetaObject::invokeMethod(plugin.get(), "BoxKey", Q_ARG(int,code), Q_ARG(bool,pressed)), "box key");
    };
    enable(); const double start_x=position().x(); key(Qt::Key_W,true); Pump(800);
    Check(position().x()>start_x+.15, "W moves actual body along +world X");
    key(Qt::Key_W,false); Pump(200); const double stopped=position().x(); Pump(250);
    Check(std::abs(position().x()-stopped)<.025, "key release stops physical box");
    key(Qt::Key_W,true); Pump(1500); key(Qt::Key_W,false); Pump(150);
    {std::lock_guard<std::mutex> l(mutex); Check(contacts>0, "real collision with fixture wall recorded");}
    Check(position().x()<1.77, "collision geometry prevents passing through wall");
    QMetaObject::invokeMethod(plugin.get(), "StopBox");
    gz::msgs::Pose reset; reset.set_name(name); reset.mutable_position()->set_x(1.); reset.mutable_position()->set_y(1.); reset.mutable_position()->set_z(.108);
    reset.mutable_orientation()->set_z(std::sin(M_PI/4)); reset.mutable_orientation()->set_w(std::cos(M_PI/4));
    gz::msgs::Boolean reply; bool ok=false;
    Check(probe.Request("/world/large_warehouse/set_pose",reset,3000,reply,ok) && ok && reply.data(), "rotate native box 90 degrees"); Pump(200);
    enable(); auto before=position(); key(Qt::Key_W,true); Pump(450); key(Qt::Key_W,false); Pump(100);
    Check(position().x()>before.x()+.08 && std::abs(position().y()-before.y())<.03,
      "world-axis controls remain correct after yaw rotation");
    QMetaObject::invokeMethod(plugin.get(), "StopBox"); Pump(100);
    auto publisher=probe.Advertise<gz::msgs::Twist>(topic); wait([&]() {return publisher.HasConnections();});
    gz::msgs::Twist velocity; velocity.mutable_linear()->set_y(-.3); publisher.Publish(velocity); Pump(650);
    const double deadman_y=position().y(); Pump(300);
    Check(std::abs(position().y()-deadman_y)<.025, "server watchdog stops when input stream disappears");
    Check(QMetaObject::invokeMethod(plugin.get(), "RemoveBox"), "remove owned native box");
    wait([&]() {return !plugin->property("hasBox").toBool() && !plugin->property("boxBusy").toBool();});
    gz::msgs::Empty request; gz::msgs::Scene scene;
    Check(probe.Request("/world/large_warehouse/scene/info",request,3000,scene,ok) && ok, "inspect remaining scene");
    bool other=false,own=false;
    for(const auto &m:scene.model()) {other=other || m.name()=="do_not_remove"; own=own || m.name()==name;}
    Check(other && !own,"only owned box removed");
    app.RemovePlugin(plugin_name.toStdString()); plugin.reset(); Pump(200);
    server.terminate(); if(!server.waitForFinished(5000)) {server.kill();server.waitForFinished(3000);}
    std::cout << "PASS: real GUI-created dimensions/collision, hold/release motion, world axes after yaw, "
              << "server deadman and owned-only removal. No robot or RL." << std::endl;
    return 0;
  } catch(const std::exception &e) {
    std::cerr << "FAIL: " << e.what() << std::endl;
    server.terminate(); if(!server.waitForFinished(5000)) {server.kill();server.waitForFinished(3000);}
    return 1;
  }
}

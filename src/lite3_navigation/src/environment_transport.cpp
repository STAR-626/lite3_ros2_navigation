// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// Read-only Gazebo scene/pose adapter; no ROS node and no world mutation APIs.
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <iostream>
#include <mutex>
#include <regex>
#include <string>
#include <unordered_map>
#include <thread>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <gz/transport/Node.hh>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/scene.pb.h>

std::atomic<bool> running{true};
void stop(int) {running = false;}
int main(int argc, char ** argv)
{
  if (argc != 2 || !std::regex_match(argv[1], std::regex("[A-Za-z0-9_-]{1,80}"))) {
    return 2;
  }
  std::signal(SIGINT, stop); std::signal(SIGTERM, stop);
  const std::string base = "/world/" + std::string(argv[1]);
  std::mutex mutex;
  std::unordered_map<unsigned int, gz::msgs::Pose> poses;
  gz::transport::Node node;
  auto updated = [&mutex, &poses](const gz::msgs::Pose_V & message) {
      std::lock_guard<std::mutex> lock(mutex);
      for (const auto & pose : message.pose()) {
        if (poses.size() < 8192 || poses.count(pose.id())) {poses[pose.id()] = pose;}
      }
    };
  node.Subscribe<gz::msgs::Pose_V>(base + "/pose/info", updated);
  while (running) {
    gz::msgs::Empty request; gz::msgs::Scene scene; bool result = false;
    bool ok = node.Request(base + "/scene/info", request, 1000, scene, result) && result;
    QJsonArray models;
    if (scene.model_size() > 256) {ok = false;}
    if (ok) {
      std::lock_guard<std::mutex> lock(mutex);
      for (const auto & model : scene.model()) {
        // Only top-level models are exported: their parent is the world frame.
        const auto found = poses.find(model.id());
        const auto & pose = found == poses.end() ? model.pose() : found->second;
        const auto & p = pose.position(); const auto & q = pose.orientation();
        const double norm = q.w()*q.w()+q.x()*q.x()+q.y()*q.y()+q.z()*q.z();
        const double yaw = std::atan2(2*(q.w()*q.z()+q.x()*q.y()),
          norm-2*(q.y()*q.y()+q.z()*q.z())) * 180.0 / std::acos(-1.0);
        if (model.name().size() > 256 || !std::isfinite(p.x()) ||
          !std::isfinite(p.y()) || !std::isfinite(p.z()) || !std::isfinite(yaw) ||
          !std::isfinite(norm) || std::abs(norm - 1.0) > .01)
        {ok = false; break;}
        models.append(QJsonObject{{"name", QString::fromStdString(model.name())},
            {"entity_id", static_cast<double>(model.id())},
            {"level", q.x()*q.x()+q.y()*q.y() < 1e-8},
            {"pose", QJsonArray{p.x(), p.y(), p.z(), yaw}}});
      }
    }
    QJsonObject snapshot{{"ok", ok}, {"world", QString::fromStdString(argv[1])},
      {"models", ok ? models : QJsonArray{}}};
    std::cout << QJsonDocument(snapshot).toJson(QJsonDocument::Compact).toStdString()
              << std::endl;
    for (int i = 0; running && i < 10; ++i) {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
  }
}

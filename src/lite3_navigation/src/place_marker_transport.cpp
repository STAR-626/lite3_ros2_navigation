// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// No ROS node/world entity: GUI-only markers. Ogre2 has no native TEXT marker;
// convert font outlines into ground-parallel line geometry (incl. Chinese).
#include <iostream>
#include <string>
#include <QGuiApplication>
#include <QFont>
#include <QPainterPath>
#include <google/protobuf/text_format.h>
#include <gz/transport/Node.hh>
#include <gz/msgs/marker.pb.h>
int main(int argc, char ** argv)
{
  qputenv("QT_QPA_PLATFORM", "offscreen");
  QGuiApplication application(argc, argv);
  const bool audit = argc == 2 && std::string(argv[1]) == "--audit";
  gz::transport::Node node;
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.size() > 65536) {continue;}
    gz::msgs::Marker marker;
    if (!google::protobuf::TextFormat::ParseFromString(line, &marker)) {continue;}
    if (marker.ns().rfind("lite3_places/", 0) != 0) {continue;}
    marker.set_visibility(gz::msgs::Marker::GUI);
    if (marker.action() == gz::msgs::Marker::ADD_MODIFY &&
      marker.type() == gz::msgs::Marker::TEXT)
    {
      QFont font(QStringLiteral("Noto Sans CJK SC")); font.setPixelSize(48);
      QPainterPath path; path.addText(0, 0, font, QString::fromUtf8(marker.text().c_str()));
      const auto bounds = path.boundingRect();
      if (bounds.height() <= 0) {continue;}
      const double scale = marker.scale().z()/bounds.height();
      const auto pose = marker.pose(); marker.clear_point();
      marker.mutable_pose()->Clear(); marker.mutable_pose()->mutable_orientation()->set_w(1.);
      marker.set_type(gz::msgs::Marker::LINE_LIST);
      marker.mutable_scale()->set_x(.012);marker.mutable_scale()->set_y(.012);marker.mutable_scale()->set_z(.012);
      for (const auto & polygon : path.toSubpathPolygons()) {
        for (int i = 1; i < polygon.size(); ++i) {
          for (int j : {i-1, i}) {
            auto * p = marker.add_point();
            p->set_x(pose.position().x()+(polygon[j].x()-bounds.center().x())*scale);
            p->set_y(pose.position().y()-(polygon[j].y()-bounds.center().y())*scale+.30);
            p->set_z(pose.position().z());
          }
        }
      }
    }
    node.Request("/marker", marker);
    if (audit) {
      google::protobuf::TextFormat::Printer printer; printer.SetSingleLineMode(true);
      std::string output; printer.PrintToString(marker, &output);
      std::cout << output << std::endl;
    }
  }
}

// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#ifndef LITE3_GAZEBO_TARGET_PICKER_HH_
#define LITE3_GAZEBO_TARGET_PICKER_HH_

#include <QString>
#include <QTimer>
#include <cstdint>
#include <gz/gui/Plugin.hh>
#include <gz/math/Vector3.hh>
#include <gz/transport/Node.hh>

class Lite3TargetPicker : public gz::gui::Plugin
{
  Q_OBJECT
  Q_PROPERTY(bool armed READ Armed NOTIFY Changed)
  Q_PROPERTY(bool hasSelection READ HasSelection NOTIFY Changed)
  Q_PROPERTY(QString status READ Status NOTIFY Changed)
  Q_PROPERTY(QString coordinates READ Coordinates NOTIFY Changed)

public:
  Lite3TargetPicker();
  ~Lite3TargetPicker() override;
  bool Armed() const { return armed_; }
  bool HasSelection() const { return selected_; }
  QString Status() const { return status_; }
  QString Coordinates() const;
  Q_INVOKABLE void Arm();
  Q_INVOKABLE void CancelPick();
  Q_INVOKABLE void CopyCoordinates();

signals:
  void Changed();

protected:
  void LoadConfig(const tinyxml2::XMLElement *config) override;
  bool eventFilter(QObject *object, QEvent *event) override;

private:
  void PublishSelection();
  void ChoosePoint(const gz::math::Vector3d &point);
  bool armed_ = false;
  bool selected_ = false;
  bool pending_click_ = false;
  double max_height_ = 0.15;
  QString status_ = QStringLiteral("点击“选择目标”，再单击地面。");
  gz::math::Vector3d point_;
  gz::math::Vector3d pending_point_;
  int64_t selected_at_ns_ = 0;
  gz::transport::Node transport_;
  gz::transport::Node::Publisher publisher_;
  QTimer timer_;
};

#endif

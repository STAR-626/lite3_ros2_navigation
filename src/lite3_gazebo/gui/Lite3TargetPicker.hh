// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#ifndef LITE3_GAZEBO_TARGET_PICKER_HH_
#define LITE3_GAZEBO_TARGET_PICKER_HH_

#include <QString>
#include <QTimer>
#include <cstdint>
#include <chrono>
#include <memory>
#include <mutex>
#include <set>
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
  Q_PROPERTY(bool hasBox READ HasBox NOTIFY BoxChanged)
  Q_PROPERTY(bool canPlaceBox READ CanPlaceBox NOTIFY BoxChanged)
  Q_PROPERTY(bool boxBusy READ BoxBusy NOTIFY BoxChanged)
  Q_PROPERTY(bool boxControl READ BoxControl NOTIFY BoxControlChanged)
  Q_PROPERTY(QString boxStatus READ BoxStatus NOTIFY BoxChanged)
  Q_PROPERTY(QString boxName READ BoxName NOTIFY BoxChanged)

public:
  Lite3TargetPicker();
  ~Lite3TargetPicker() override;
  bool Armed() const { return armed_; }
  bool HasSelection() const { return selected_; }
  QString Status() const { return status_; }
  QString Coordinates() const;
  bool HasBox() const {return has_box_ && !uncertain_;}
  bool BoxBusy() const {return box_busy_;}
  bool CanPlaceBox() const {return !has_box_ && !box_busy_ && !uncertain_;}
  bool BoxControl() const {return box_control_;}
  QString BoxStatus() const {return box_status_;}
  QString BoxName() const {return QString::fromStdString(box_name_);}
  Q_INVOKABLE void ArmBox(double length, double width, double height, double speed);
  Q_INVOKABLE void SetBoxSpeed(double speed);
  Q_INVOKABLE void SetBoxControl(bool enabled);
  Q_INVOKABLE void BoxKey(int key, bool pressed);
  Q_INVOKABLE void StopBox();
  Q_INVOKABLE void RemoveBox();
  Q_INVOKABLE void RefreshBox();
  Q_INVOKABLE void Arm();
  Q_INVOKABLE void CancelPick();
  Q_INVOKABLE void CopyCoordinates();

signals:
  void Changed();
  void BoxChanged();
  void BoxControlChanged();

protected:
  void LoadConfig(const tinyxml2::XMLElement *config) override;
  bool eventFilter(QObject *object, QEvent *event) override;

private:
  using Clock = std::chrono::steady_clock;
  struct Reply {
    std::mutex mutex;
    bool done = false, ok = false, exists = false;
    std::string kind;
  };
  void TickBox();
  void PublishBoxVelocity();
  void SpawnBox(const gz::math::Vector3d & point);
  void QueryBox();
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
  QTimer timer_, box_timer_;
  bool box_pick_ = false, has_box_ = false, box_busy_ = false;
  bool box_control_ = false, uncertain_ = false;
  double box_length_ = .4, box_width_ = .4, box_height_ = .4, box_speed_ = .15;
  std::set<int> held_;
  std::string world_ = "large_warehouse", box_name_, box_topic_, operation_;
  QString box_status_ = QStringLiteral("设置尺寸后点击放置箱子，再单击地面。");
  gz::transport::Node::Publisher box_publisher_;
  std::shared_ptr<Reply> reply_;
  Clock::time_point deadline_{}, next_query_{};
};

#endif

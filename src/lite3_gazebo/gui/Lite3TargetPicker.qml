// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
import QtQuick 2.12
import QtQuick.Controls 2.5
import QtQuick.Layouts 1.12

Rectangle {
  color: "#fafafa"
  implicitWidth: 330
  implicitHeight: 410
  Layout.minimumWidth: 300
  Layout.minimumHeight: 400
  ColumnLayout {
    anchors.fill: parent
    anchors.margins: 12
    spacing: 10
    Label {
      text: "选择导航目标，执行状态见终端"
      font.bold: true
      Layout.fillWidth: true
      wrapMode: Text.WordWrap
    }
    RowLayout {
      Button {
        objectName: "armButton"
        text: Lite3TargetPicker.armed ? "等待点击地面…" : "选择目标"
        highlighted: true
        enabled: !Lite3TargetPicker.armed
        background: Rectangle {
          radius: 4
          color: parent.enabled ? "#1565c0" : "#d7dce2"
        }
        contentItem: Text {
          text: parent.text
          color: parent.enabled ? "white" : "#5b6573"
          font: parent.font
          horizontalAlignment: Text.AlignHCenter
          verticalAlignment: Text.AlignVCenter
        }
        onClicked: Lite3TargetPicker.Arm()
      }
      Button {
        text: "取消选点"
        enabled: Lite3TargetPicker.armed
        onClicked: Lite3TargetPicker.CancelPick()
      }
    }
    Label {
      text: Lite3TargetPicker.coordinates
      font.pixelSize: 19
      Layout.fillWidth: true
      wrapMode: Text.WordWrap
    }
    Button {
      text: "复制坐标"
      enabled: Lite3TargetPicker.hasSelection
      onClicked: Lite3TargetPicker.CopyCoordinates()
    }
    Label {
      text: Lite3TargetPicker.status
      Layout.fillWidth: true
      wrapMode: Text.WordWrap
    }
    Item { Layout.fillHeight: true }
    Label {
      text: "总开关开启后，新选点立即导航。\n忙碌时的新选点不会排队。"
      color: "#795548"
      Layout.fillWidth: true
      wrapMode: Text.WordWrap
    }
  }
}

// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
import QtQuick 2.12
import QtQuick.Controls 2.5
import QtQuick.Layouts 1.12

Rectangle {
  id: root
  color: "#fafafa"
  implicitWidth: 370
  implicitHeight: 640
  Layout.minimumWidth: 320
  Layout.minimumHeight: 420
  onVisibleChanged: if (!visible) Lite3TargetPicker.StopBox()
  Connections {
    target: Lite3TargetPicker
    onBoxControlChanged: {
      if (Lite3TargetPicker.boxControl) controlPad.forceActiveFocus()
    }
  }
  ColumnLayout {
    anchors.fill: parent
    anchors.margins: 10
    spacing: 8
    TabBar {
      id: tabs
      objectName: "modeTabs"
      Layout.fillWidth: true
      onCurrentIndexChanged: {
        Lite3TargetPicker.CancelPick()
        Lite3TargetPicker.StopBox()
      }
      TabButton { text: "导航目标" }
      TabButton { text: "动态箱子" }
    }
    StackLayout {
      currentIndex: tabs.currentIndex
      Layout.fillWidth: true
      Layout.fillHeight: true
      ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
          width: parent.width
          spacing: 10
          Label { text: "选择机器狗的导航目标"; font.bold: true; Layout.fillWidth: true }
          RowLayout {
            Button {
              objectName: "armButton"
              text: Lite3TargetPicker.armed ? "等待点击地面…" : "选择目标"
              enabled: !Lite3TargetPicker.armed
              background: Rectangle { radius: 4; color: parent.enabled ? "#1565c0" : "#d7dce2" }
              contentItem: Text {
                text: parent.text; color: parent.enabled ? "white" : "#5b6573"; font: parent.font
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
              }
              onClicked: Lite3TargetPicker.Arm()
            }
            Button { text: "取消"; enabled: Lite3TargetPicker.armed; onClicked: Lite3TargetPicker.CancelPick() }
          }
          Label {
            text: Lite3TargetPicker.coordinates; font.pixelSize: 19
            Layout.fillWidth: true; wrapMode: Text.WordWrap
          }
          Button { text: "复制坐标"; enabled: Lite3TargetPicker.hasSelection; onClicked: Lite3TargetPicker.CopyCoordinates() }
          Label { text: Lite3TargetPicker.status; Layout.fillWidth: true; wrapMode: Text.WordWrap }
          Label {
            text: "总开关开启且空闲时，新选点立即导航。\n忙碌时的新选点不会排队。"
            color: "#795548"; Layout.fillWidth: true; wrapMode: Text.WordWrap
          }
        }
      }
      ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
          width: parent.width
          spacing: 5
          Label { text: "可移动测试箱子（单位：米）"; font.bold: true }
          GridLayout {
            columns: 3
            Layout.fillWidth: true
            Label { text: "长 X" }
            Label { text: "宽 Y" }
            Label { text: "高 Z" }
            TextField { id: boxLength; objectName: "boxLength"; text: "0.4"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 80; enabled: Lite3TargetPicker.canPlaceBox; validator: DoubleValidator { bottom: 0.1; top: 2.0; locale: "C" } }
            TextField { id: boxWidth; text: "0.4"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 80; enabled: boxLength.enabled; validator: DoubleValidator { bottom: 0.1; top: 2.0; locale: "C" } }
            TextField { id: boxHeight; text: "0.4"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 80; enabled: boxLength.enabled; validator: DoubleValidator { bottom: 0.1; top: 2.0; locale: "C" } }
          }
          RowLayout {
            Label { text: "速度 m/s" }
            TextField {
              id: boxSpeed; objectName: "boxSpeed"; text: "0.15"; Layout.fillWidth: true
              enabled: !Lite3TargetPicker.boxBusy
              validator: DoubleValidator { bottom: 0.05; top: 0.5; locale: "C" }
              onEditingFinished: Lite3TargetPicker.SetBoxSpeed(Number(text))
            }
          }
          RowLayout {
            Button {
              objectName: "placeBoxButton"
              text: "点击地面放箱子"
              enabled: Lite3TargetPicker.canPlaceBox
              onClicked: Lite3TargetPicker.ArmBox(Number(boxLength.text), Number(boxWidth.text), Number(boxHeight.text), Number(boxSpeed.text))
            }
            Button { text: "取消"; enabled: Lite3TargetPicker.armed; onClicked: Lite3TargetPicker.CancelPick() }
          }
          Button {
            objectName: "boxControlButton"
            Layout.fillWidth: true
            text: Lite3TargetPicker.boxControl ? "退出箱子控制" : "启用箱子控制（WASD）"
            enabled: Lite3TargetPicker.hasBox && !Lite3TargetPicker.boxBusy
            onClicked: Lite3TargetPicker.SetBoxControl(!Lite3TargetPicker.boxControl)
          }
          Rectangle {
            id: controlPad
            objectName: "boxControlPad"
            Layout.fillWidth: true
            Layout.preferredHeight: 140
            focus: false
            color: Lite3TargetPicker.boxControl ? "#e8f5e9" : "#eeeeee"
            border.color: Lite3TargetPicker.boxControl ? "#2e7d32" : "#bdbdbd"
            border.width: 2
            radius: 5
            onActiveFocusChanged: if (!activeFocus && Lite3TargetPicker.boxControl) Lite3TargetPicker.StopBox()
            Keys.onPressed: {
              if (Lite3TargetPicker.boxControl && [Qt.Key_W, Qt.Key_S, Qt.Key_A, Qt.Key_D, Qt.Key_Space, Qt.Key_Escape].indexOf(event.key) >= 0) {
                event.accepted = true
                if (!event.isAutoRepeat) Lite3TargetPicker.BoxKey(event.key, true)
              }
            }
            Keys.onReleased: {
              if (Lite3TargetPicker.boxControl && [Qt.Key_W, Qt.Key_S, Qt.Key_A, Qt.Key_D].indexOf(event.key) >= 0) {
                event.accepted = true
                if (!event.isAutoRepeat) Lite3TargetPicker.BoxKey(event.key, false)
              }
            }
            ColumnLayout {
              anchors.centerIn: parent
              spacing: 1
              Button {
                text: "W  +X"; focusPolicy: Qt.NoFocus; Layout.alignment: Qt.AlignHCenter
                enabled: Lite3TargetPicker.boxControl
                onPressed: Lite3TargetPicker.BoxKey(Qt.Key_W, true)
                onReleased: Lite3TargetPicker.BoxKey(Qt.Key_W, false)
                onCanceled: Lite3TargetPicker.BoxKey(Qt.Key_W, false)
              }
              RowLayout {
                Button {
                  text: "A  +Y"; focusPolicy: Qt.NoFocus; enabled: Lite3TargetPicker.boxControl
                  onPressed: Lite3TargetPicker.BoxKey(Qt.Key_A, true)
                  onReleased: Lite3TargetPicker.BoxKey(Qt.Key_A, false)
                  onCanceled: Lite3TargetPicker.BoxKey(Qt.Key_A, false)
                }
                Button { text: "停止"; objectName: "stopBoxButton"; focusPolicy: Qt.NoFocus; onClicked: Lite3TargetPicker.StopBox() }
                Button {
                  text: "D  −Y"; focusPolicy: Qt.NoFocus; enabled: Lite3TargetPicker.boxControl
                  onPressed: Lite3TargetPicker.BoxKey(Qt.Key_D, true)
                  onReleased: Lite3TargetPicker.BoxKey(Qt.Key_D, false)
                  onCanceled: Lite3TargetPicker.BoxKey(Qt.Key_D, false)
                }
              }
              Button {
                text: "S  −X"; focusPolicy: Qt.NoFocus; Layout.alignment: Qt.AlignHCenter
                enabled: Lite3TargetPicker.boxControl
                onPressed: Lite3TargetPicker.BoxKey(Qt.Key_S, true)
                onReleased: Lite3TargetPicker.BoxKey(Qt.Key_S, false)
                onCanceled: Lite3TargetPicker.BoxKey(Qt.Key_S, false)
              }
            }
          }
          RowLayout {
            Button { text: "移除箱子"; objectName: "removeBoxButton"; enabled: Lite3TargetPicker.hasBox && !Lite3TargetPicker.boxBusy; onClicked: Lite3TargetPicker.RemoveBox() }
            Button { text: "检查状态"; enabled: !Lite3TargetPicker.boxBusy; onClicked: Lite3TargetPicker.RefreshBox() }
          }
          Label { text: Lite3TargetPicker.boxStatus; Layout.fillWidth: true; wrapMode: Text.WordWrap }
          Label {
            text: "世界坐标方向；切页或失焦会停车。\n仅控制箱子，不控制机器狗。"
            color: "#795548"; Layout.fillWidth: true; wrapMode: Text.WordWrap
          }
        }
      }
    }
  }
}

import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "engines.js" as EnginesJs
import "settings.js" as Settings
import "screens.js" as Screens

ColumnLayout {
  id: root

  property string nativeLanguage: "none"
  property string targetEnglish: "en-US"
  property string engine: "harper"
  property bool autoReplace: false
  property bool wholeTextbox: false
  property string quickHotkey: "SUPER + SHIFT + Q"
  property string composeHotkey: "SUPER + ALT + Q"
  property string popupScreen: ""
  property var screens: []

  property var engines: []
  property string engineBusy: ""
  property double engineBusyBytes: 0
  property bool enginesBusy: false
  property string engineConfirm: ""
  property string enginesDirectory: ""
  property double enginesFreeBytes: 0
  property var engineNote: null
  property var dependencies: []

  signal settingChanged(string name, var value)
  signal engineInstallRequested(string slug)
  signal engineCancelRequested()
  signal engineRemoveRequested(string slug)
  signal engineRemoveConfirmed(string slug)
  signal engineKeepRequested()

  // Dropdown writes its own `value` when the user picks a row, which drops the
  // declarative binding. Re-asserting it on every change of the stored value
  // is what keeps the view live for a write from outside, such as
  // `omarchy-shell shell setBarWidget <id> engine '"harper"'`.
  onNativeLanguageChanged: nativeLanguageDropdown.value = root.nativeLanguage
  onTargetEnglishChanged: targetEnglishDropdown.value = root.targetEnglish
  onEngineChanged: engineDropdown.value = root.engine
  // The option list narrows as the Engines list lands, and a Dropdown that
  // has written its own `value` once no longer follows the binding, so the
  // value is re-asserted when the rows move as well as when the setting does.
  onEnginesChanged: engineDropdown.value = root.engine
  // A TextField that has typed its own `text` once no longer follows the
  // binding either, so a live external write, such as a hand edit of
  // shell.json, is re-asserted the same way.
  onQuickHotkeyChanged: quickHotkeyField.text = root.quickHotkey
  onComposeHotkeyChanged: composeHotkeyField.text = root.composeHotkey

  spacing: Style.spacing.lg

  Text {
    Layout.fillWidth: true
    text: "Every change is kept at once and applies to the next check."
    color: Color.muted
    wrapMode: Text.Wrap
    font.family: Style.font.family
    font.pixelSize: Style.font.bodySmall
  }

  RowLayout {
    Layout.fillWidth: true
    spacing: Style.spacing.xxl

    Dropdown {
      id: nativeLanguageDropdown

      Layout.fillWidth: true
      label: "Native language"
      options: Settings.NATIVE_LANGUAGE_OPTIONS
      value: root.nativeLanguage
      foreground: Color.popups.text
      background: Color.popups.background
      onChanged: function(value) { root.settingChanged("nativeLanguage", Settings.normalised("nativeLanguage", value)) }
    }

    Dropdown {
      id: targetEnglishDropdown

      Layout.fillWidth: true
      label: "Target English"
      options: Settings.TARGET_ENGLISH_OPTIONS
      value: root.targetEnglish
      foreground: Color.popups.text
      background: Color.popups.background
      onChanged: function(value) { root.settingChanged("targetEnglish", Settings.normalised("targetEnglish", value)) }
    }

    // Spec section 7 and HUF-237: only an engine this machine has is offered.
    // The Engines list below is where a missing one is added.
    Dropdown {
      id: engineDropdown

      Layout.fillWidth: true
      label: "Engine"
      options: Settings.engineOptions(EnginesJs.unavailable(root.engines), root.engine)
      value: root.engine
      foreground: Color.popups.text
      background: Color.popups.background
      onChanged: function(value) { root.settingChanged("engine", Settings.normalised("engine", value)) }
    }
  }

  // Spec section 2: the two trigger hotkeys, remappable text fields rather
  // than a dropdown, because a Hyprland key combination is free text. A
  // change reaches `~/.config/hypr/bindings.lua` and the compositor through
  // `Overlay.applyHotkeys`, not through this view.
  RowLayout {
    Layout.fillWidth: true
    spacing: Style.spacing.xxl

    ColumnLayout {
      Layout.fillWidth: true
      spacing: Style.spacing.labelGap

      Text {
        text: "Quick popup hotkey"
        color: Qt.darker(Color.popups.text, 1.4)
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        font.bold: true
      }

      TextField {
        id: quickHotkeyField

        Layout.fillWidth: true
        text: root.quickHotkey
        foreground: Color.popups.text
        onEditingFinished: {
          var value = Settings.normalised("quickHotkey", quickHotkeyField.text)
          if (value !== root.quickHotkey) root.settingChanged("quickHotkey", value)
          quickHotkeyField.text = value
        }
      }
    }

    ColumnLayout {
      Layout.fillWidth: true
      spacing: Style.spacing.labelGap

      Text {
        text: "Compose hotkey"
        color: Qt.darker(Color.popups.text, 1.4)
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        font.bold: true
      }

      TextField {
        id: composeHotkeyField

        Layout.fillWidth: true
        text: root.composeHotkey
        foreground: Color.popups.text
        onEditingFinished: {
          var value = Settings.normalised("composeHotkey", composeHotkeyField.text)
          if (value !== root.composeHotkey) root.settingChanged("composeHotkey", value)
          composeHotkeyField.text = value
        }
      }
    }
  }

  Toggle {
    Layout.fillWidth: true
    label: "Auto-replace"
    description: "Replaces the highlighted text by pasting over it"
    checked: root.autoReplace
    foreground: Color.popups.text
    onClicked: root.settingChanged("autoReplace", !root.autoReplace)
  }

  Toggle {
    Layout.fillWidth: true
    label: "Check whole textbox"
    description: "With nothing highlighted, check all of the text you are typing in"
    checked: root.wholeTextbox
    foreground: Color.popups.text
    onClicked: root.settingChanged("wholeTextbox", !root.wholeTextbox)
  }

  // The quick popup opens centred on the monitor picked here. The rows are
  // `ui/screens.js`'s miniature of the global layout and this view only
  // paints them, so a click says which output `Overlay.applyPopupScreen`
  // should move the panel to. Picks apply the next time the popup opens:
  // the panel is only ever moved while it is hidden.
  ColumnLayout {
    Layout.fillWidth: true
    spacing: Style.spacing.labelGap

    Text {
      text: "Popup screen"
      color: Qt.darker(Color.popups.text, 1.4)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      font.bold: true
    }

    Text {
      Layout.fillWidth: true
      text: "The quick popup opens centred on the monitor you click. Auto keeps whichever screen the panel was on. Picks apply the next time the popup opens."
      color: Color.muted
      wrapMode: Text.Wrap
      font.family: Style.font.family
      font.pixelSize: Style.font.bodySmall
    }

    Item {
      id: pickerBox

      Layout.fillWidth: true
      Layout.preferredHeight: Style.space(96)

      property real boxWidth: width
      property real boxHeight: height
      readonly property var rows: Screens.layoutOf(root.screens, { width: boxWidth, height: boxHeight })

      Repeater {
        model: pickerBox.rows

        delegate: Rectangle {
          required property var modelData

          x: modelData.x
          y: modelData.y
          width: modelData.width
          height: modelData.height
          radius: 2
          color: modelData.name === root.popupScreen ? Qt.alpha(Color.accent, 0.35) : Qt.alpha(Color.popups.text, 0.08)
          border.color: modelData.name === root.popupScreen ? Color.accent : Color.popups.border
          border.width: modelData.name === root.popupScreen ? 2 : 1

          Text {
            anchors.centerIn: parent
            width: Math.min(implicitWidth, parent.width - 4)
            text: modelData.name
            textFormat: Text.PlainText
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            elide: Text.ElideMiddle
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.settingChanged("popupScreen", modelData.name)
          }
        }
      }
    }

    Rectangle {
      Layout.preferredWidth: autoLabel.implicitWidth + Style.space(16)
      Layout.preferredHeight: autoLabel.implicitHeight + Style.space(8)
      radius: 4
      color: root.popupScreen === "" ? Qt.alpha(Color.accent, 0.35) : Qt.alpha(Color.popups.text, 0.08)
      border.color: root.popupScreen === "" ? Color.accent : Color.popups.border
      border.width: root.popupScreen === "" ? 2 : 1

      Text {
        id: autoLabel

        anchors.centerIn: parent
        text: "Auto"
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
      }

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.settingChanged("popupScreen", "")
      }
    }
  }

  EnginesView {
    Layout.fillWidth: true

    engines: root.engines
    busy: root.engineBusy
    busyBytes: root.engineBusyBytes
    working: root.enginesBusy
    confirmSlug: root.engineConfirm
    selected: root.engine
    directory: root.enginesDirectory
    freeBytes: root.enginesFreeBytes
    note: root.engineNote
    dependencies: root.dependencies

    onInstall: function(slug) { root.engineInstallRequested(slug) }
    onCancel: root.engineCancelRequested()
    onRemove: function(slug) { root.engineRemoveRequested(slug) }
    onConfirmRemove: function(slug) { root.engineRemoveConfirmed(slug) }
    onKeepEngine: root.engineKeepRequested()
  }
}

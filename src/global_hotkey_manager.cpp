#include "global_hotkey_manager.h"

#include <QCoreApplication>
#include <QMetaObject>
#include <QTimer>
#include <QWindow>

#ifdef Q_OS_WIN
#include <qt_windows.h>
#endif


namespace {

enum HotkeyId {
    PlayPauseHotkey = 1,
    NextHotkey,
    LockHotkey,
    SeekBackwardHotkey,
    SeekForwardHotkey
};

#ifdef Q_OS_WIN
int actionForNumpadScanCode(USHORT scanCode, USHORT flags)
{
    if ((flags & (RI_KEY_E0 | RI_KEY_E1)) != 0) {
        return 0;
    }
    switch (scanCode) {
    case 0x4B:
        return NextHotkey;
    case 0x4C:
        return PlayPauseHotkey;
    case 0x4D:
        return LockHotkey;
    case 0x4F:
        return SeekBackwardHotkey;
    case 0x51:
        return SeekForwardHotkey;
    default:
        return 0;
    }
}
#endif

}


GlobalHotkeyManager::GlobalHotkeyManager(QObject *parent)
    : QObject(parent)
{
}


GlobalHotkeyManager::~GlobalHotkeyManager()
{
#ifdef Q_OS_WIN
    if (m_rawInputRegistered) {
        RAWINPUTDEVICE keyboard = {};
        keyboard.usUsagePage = 0x01;
        keyboard.usUsage = 0x06;
        keyboard.dwFlags = RIDEV_REMOVE;
        keyboard.hwndTarget = nullptr;
        RegisterRawInputDevices(&keyboard, 1, sizeof(keyboard));
        m_rawInputRegistered = false;
    }
    if (m_nativeEventFilterInstalled && QCoreApplication::instance()) {
        QCoreApplication::instance()->removeNativeEventFilter(this);
        m_nativeEventFilterInstalled = false;
    }
    if (m_inputWindow) {
        m_inputWindow->destroy();
        delete m_inputWindow;
        m_inputWindow = nullptr;
    }
#endif
}


QStringList GlobalHotkeyManager::registerHotkeys()
{
    QStringList failures;
#ifdef Q_OS_WIN
    if (m_rawInputRegistered) {
        return failures;
    }

    m_inputWindow = new QWindow;
    m_inputWindow->setFlags(Qt::Tool);
    m_inputWindow->create();

    RAWINPUTDEVICE keyboard = {};
    keyboard.usUsagePage = 0x01;
    keyboard.usUsage = 0x06;
    keyboard.dwFlags = RIDEV_INPUTSINK;
    keyboard.hwndTarget = reinterpret_cast<HWND>(m_inputWindow->winId());
    if (!RegisterRawInputDevices(&keyboard, 1, sizeof(keyboard))) {
        failures.append(QStringLiteral("左Ctrl+Num1/3/4/5/6（Raw Input 错误 %1）")
                            .arg(GetLastError()));
        m_inputWindow->destroy();
        delete m_inputWindow;
        m_inputWindow = nullptr;
        return failures;
    }

    m_rawInputRegistered = true;
    QCoreApplication::instance()->installNativeEventFilter(this);
    m_nativeEventFilterInstalled = true;
#else
    failures.append(QStringLiteral("当前系统不支持 Windows 全局快捷键"));
#endif
    return failures;
}


bool GlobalHotkeyManager::nativeEventFilter(
    const QByteArray &eventType, void *message, long *result)
{
    Q_UNUSED(eventType)
    Q_UNUSED(result)
#ifdef Q_OS_WIN
    const auto *nativeMessage = static_cast<const MSG *>(message);
    if (nativeMessage && nativeMessage->message == WM_INPUT) {
        handleRawInput(reinterpret_cast<void *>(nativeMessage->lParam));
    }
#else
    Q_UNUSED(message)
#endif
    return false;
}


void GlobalHotkeyManager::handleRawInput(void *rawInputHandle)
{
#ifdef Q_OS_WIN
    RAWINPUT input = {};
    UINT inputSize = sizeof(input);
    const UINT bytesRead = GetRawInputData(
        reinterpret_cast<HRAWINPUT>(rawInputHandle), RID_INPUT,
        &input, &inputSize, sizeof(RAWINPUTHEADER));
    if (bytesRead == static_cast<UINT>(-1)
        || input.header.dwType != RIM_TYPEKEYBOARD) {
        return;
    }

    const RAWKEYBOARD &keyboard = input.data.keyboard;
    const bool released = (keyboard.Flags & RI_KEY_BREAK) != 0;
    if (keyboard.MakeCode == 0x1D) {
        const bool rightControl = (keyboard.Flags & RI_KEY_E0) != 0;
        if (rightControl) {
            return;
        }
        m_leftControlDown = !released;
        if (released) {
            for (bool &down : m_keyDown) {
                down = false;
            }
            QMetaObject::invokeMethod(this, [this]() {
                releaseAllHotkeys();
            }, Qt::QueuedConnection);
        }
        return;
    }

    const int action = actionForNumpadScanCode(keyboard.MakeCode, keyboard.Flags);
    if (action == 0) {
        return;
    }
    if (released) {
        if (m_keyDown[action]) {
            m_keyDown[action] = false;
            QMetaObject::invokeMethod(this, [this, action]() {
                endHotkey(action);
            }, Qt::QueuedConnection);
        }
        return;
    }
    if (!m_leftControlDown
        || (m_playbackOnlyMode && action != PlayPauseHotkey)
        || m_keyDown[action]) {
        return;
    }

    m_keyDown[action] = true;
    QMetaObject::invokeMethod(this, [this, action]() {
        beginHotkey(action);
    }, Qt::QueuedConnection);
#else
    Q_UNUSED(rawInputHandle)
#endif
}


bool GlobalHotkeyManager::isPlaybackOnlyMode() const
{
    return m_playbackOnlyMode;
}


void GlobalHotkeyManager::beginHotkey(int action)
{
    if (action <= 0 || action >= 6
        || (m_playbackOnlyMode && action != PlayPauseHotkey)) {
        return;
    }

    const quint64 generation = ++m_pressGeneration[action];
    dispatchHotkey(action);
    if (action == SeekBackwardHotkey
        || action == SeekForwardHotkey
        || action == NextHotkey) {
        scheduleRepeat(action, generation, 500);
    }
}


void GlobalHotkeyManager::endHotkey(int action)
{
    if (action > 0 && action < 6) {
        ++m_pressGeneration[action];
    }
}


void GlobalHotkeyManager::releaseAllHotkeys()
{
    for (quint64 &generation : m_pressGeneration) {
        ++generation;
    }
    for (bool &down : m_keyDown) {
        down = false;
    }
}


void GlobalHotkeyManager::setPlaybackOnlyMode(bool enabled)
{
    if (m_playbackOnlyMode == enabled) {
        return;
    }
    m_playbackOnlyMode = enabled;
    releaseAllHotkeys();
}


void GlobalHotkeyManager::dispatchHotkey(int action)
{
    switch (action) {
    case PlayPauseHotkey:
        emit playPauseRequested();
        break;
    case NextHotkey:
        emit nextRequested();
        break;
    case LockHotkey:
        emit lockToggleRequested();
        break;
    case SeekBackwardHotkey:
        emit seekBackwardRequested();
        break;
    case SeekForwardHotkey:
        emit seekForwardRequested();
        break;
    default:
        break;
    }
}


void GlobalHotkeyManager::scheduleRepeat(int action, quint64 generation, int delayMs)
{
    QTimer::singleShot(delayMs, this, [this, action, generation]() {
        if (action <= 0 || action >= 6
            || m_pressGeneration[action] != generation
            || m_playbackOnlyMode) {
            return;
        }

        dispatchHotkey(action);
        const int repeatInterval = action == NextHotkey ? 700 : 200;
        scheduleRepeat(action, generation, repeatInterval);
    });
}

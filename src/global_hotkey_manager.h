#pragma once

#include <QAbstractNativeEventFilter>
#include <QObject>
#include <QStringList>

class QWindow;


class GlobalHotkeyManager : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT

public:
    explicit GlobalHotkeyManager(QObject *parent = nullptr);
    ~GlobalHotkeyManager() override;

    QStringList registerHotkeys();
    bool isPlaybackOnlyMode() const;
    bool nativeEventFilter(const QByteArray &eventType,
                           void *message, long *result) override;

public slots:
    void beginHotkey(int action);
    void endHotkey(int action);
    void releaseAllHotkeys();
    void setPlaybackOnlyMode(bool enabled);

signals:
    void playPauseRequested();
    void nextRequested();
    void lockToggleRequested();
    void seekBackwardRequested();
    void seekForwardRequested();

private:
    void handleRawInput(void *rawInputHandle);
    void dispatchHotkey(int action);
    void scheduleRepeat(int action, quint64 generation, int delayMs);

    QWindow *m_inputWindow = nullptr;
    quint64 m_pressGeneration[6] = {};
    bool m_keyDown[6] = {};
    bool m_leftControlDown = false;
    bool m_rawInputRegistered = false;
    bool m_nativeEventFilterInstalled = false;
    bool m_playbackOnlyMode = false;
};

#include "global_hotkey_manager.h"
#include "lyrics_window.h"
#include "player_controller.h"

#include <QAction>
#include <QApplication>
#include <QDebug>
#include <QDesktopServices>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QIcon>
#include <QLabel>
#include <QMenu>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSharedMemory>
#include <QSystemTrayIcon>
#include <QUrl>
#include <QVBoxLayout>


int main(int argc, char *argv[])
{
    QApplication application(argc, argv);
    QApplication::setApplicationName(QStringLiteral("On Screen Music"));
    QFile versionFile(QStringLiteral(":/VERSION"));
    versionFile.open(QIODevice::ReadOnly);
    QApplication::setApplicationVersion(QString::fromUtf8(versionFile.readAll()).trimmed());
    QApplication::setOrganizationName(QStringLiteral("Inseven"));
    QApplication::setWindowIcon(QIcon(QStringLiteral(":/app_icon.png")));
    QApplication::setQuitOnLastWindowClosed(false);

    QSharedMemory singleInstance(QStringLiteral("OnScreenMusic.v1.SingleInstance"));
    if (!singleInstance.create(1)) {
        const bool alreadyRunning = singleInstance.error() == QSharedMemory::AlreadyExists;
        QMessageBox::information(
            nullptr,
            alreadyRunning ? QStringLiteral("程序已运行") : QStringLiteral("启动失败"),
            alreadyRunning
                ? QStringLiteral("On Screen Music 已经在运行。")
                : QStringLiteral("无法创建单实例标记：%1")
                      .arg(singleInstance.errorString()));
        return 0;
    }

    LyricsWindow window;
    PlayerController controller;

    QSystemTrayIcon tray(QApplication::windowIcon(), &application);
    tray.setToolTip(QStringLiteral("On Screen Music"));
    QMenu trayMenu;
    QAction *playbackOnlyAction = trayMenu.addAction(QStringLiteral("全部快捷"));
    QAction *workshopAction = trayMenu.addAction(QStringLiteral("音乐管理"));
    trayMenu.addSeparator();
    QAction *lockAction = trayMenu.addAction(QStringLiteral("锁定窗口"));
    QAction *visibilityAction = trayMenu.addAction(QStringLiteral("隐藏窗口"));
    trayMenu.addSeparator();
    QAction *aboutAction = trayMenu.addAction(QStringLiteral("软件说明"));
    QAction *quitAction = trayMenu.addAction(QStringLiteral("退出软件"));
    tray.setContextMenu(&trayMenu);

    QObject::connect(&controller, &PlayerController::lyricChanged,
                     &window, &LyricsWindow::setLyric);
    QObject::connect(&controller, &PlayerController::trackChanged,
                     &window, &LyricsWindow::setTrack);
    QObject::connect(&controller, &PlayerController::playbackChanged,
                     &window, &LyricsWindow::setPlaybackState);
    QObject::connect(&controller, &PlayerController::playbackPositionChanged,
                     &window, &LyricsWindow::setPlaybackPosition);
    QObject::connect(&controller, &PlayerController::volumeChanged,
                     &window, &LyricsWindow::setVolume);
    QObject::connect(&controller, &PlayerController::singleRepeatChanged,
                     &window, &LyricsWindow::setSingleRepeat);
    QObject::connect(&controller, &PlayerController::songsChanged,
                     &window, &LyricsWindow::setSongs);
    QObject::connect(&controller, &PlayerController::playlistsChanged,
                     &window, &LyricsWindow::setPlaylists);
    QObject::connect(&controller, &PlayerController::playlistLoadWarnings,
                     &application,
                     [](const QString &playlistName,
                        const QStringList &warnings,
                        int loadedSongCount) {
                         QDialog warningDialog;
                         warningDialog.setWindowTitle(QStringLiteral("歌单检查"));
                         warningDialog.setWindowFlag(Qt::WindowStaysOnTopHint);
                         warningDialog.setModal(true);
                         warningDialog.resize(900, 520);

                         auto *summaryLabel = new QLabel(
                             QStringLiteral("%1 加载时发现 %2 个问题，已载入 %3 首歌曲。")
                                 .arg(playlistName)
                                 .arg(warnings.size())
                                 .arg(loadedSongCount),
                             &warningDialog);
                         summaryLabel->setWordWrap(true);

                         auto *details = new QPlainTextEdit(&warningDialog);
                         details->setReadOnly(true);
                         details->setLineWrapMode(QPlainTextEdit::NoWrap);
                         details->setPlainText(warnings.join(QLatin1Char('\n')));

                         auto *buttons = new QDialogButtonBox(
                             QDialogButtonBox::Close, &warningDialog);
                         buttons->button(QDialogButtonBox::Close)
                             ->setText(QStringLiteral("关闭"));
                         QObject::connect(buttons, &QDialogButtonBox::rejected,
                                          &warningDialog, &QDialog::reject);

                         auto *layout = new QVBoxLayout(&warningDialog);
                         layout->setContentsMargins(16, 14, 16, 14);
                         layout->setSpacing(10);
                         layout->addWidget(summaryLabel);
                         layout->addWidget(details, 1);
                         layout->addWidget(buttons);
                         warningDialog.exec();
                     },
                     Qt::QueuedConnection);
    QObject::connect(&controller, &PlayerController::errorMessage,
                     &application, [&tray](const QString &message) {
                         qWarning().noquote() << message;
                         tray.showMessage(QStringLiteral("On Screen Music"), message,
                                          QSystemTrayIcon::Warning, 5000);
                     });

    QObject::connect(&window, &LyricsWindow::playPauseRequested,
                     &controller, &PlayerController::togglePlayback);
    QObject::connect(&window, &LyricsWindow::nextRequested,
                     &controller, &PlayerController::playRandom);
    QObject::connect(&window, &LyricsWindow::singleRepeatRequested,
                     &controller, &PlayerController::setSingleRepeat);
    QObject::connect(&window, &LyricsWindow::seekRequested,
                     &controller, &PlayerController::seek);
    QObject::connect(&window, &LyricsWindow::volumeRequested,
                     &controller, &PlayerController::setVolume);
    QObject::connect(&window, &LyricsWindow::songRequested,
                     &controller, &PlayerController::playSong);
    QObject::connect(&window, &LyricsWindow::playlistRequested,
                     &controller, &PlayerController::selectPlaylist);
    QObject::connect(&window, &LyricsWindow::refreshRequested,
                     &controller, &PlayerController::refreshLibrary);
    QObject::connect(&window, &LyricsWindow::closeRequested,
                     &application, &QApplication::quit);
    QObject::connect(&window, &LyricsWindow::lockedChanged,
                     &application, [lockAction](bool locked) {
                         lockAction->setText(locked ? QStringLiteral("解锁窗口")
                                                    : QStringLiteral("锁定窗口"));
                     });

    QObject::connect(lockAction, &QAction::triggered, &window, &LyricsWindow::toggleLocked);
    QObject::connect(workshopAction, &QAction::triggered, &application, [&window]() {
        const QDir directory(QCoreApplication::applicationDirPath());
        QString launcher = directory.filePath(QStringLiteral("MusicWorkshop.exe"));
        if (!QFileInfo::exists(launcher)) {
            launcher = directory.filePath(QStringLiteral("MusicWorkshop.vbs"));
        }
        if (!QFileInfo::exists(launcher)
            || !QDesktopServices::openUrl(QUrl::fromLocalFile(launcher))) {
            QMessageBox::warning(
                &window, QStringLiteral("音乐管理"),
                QStringLiteral("无法打开音乐管理。请将 MusicWorkshop 启动文件和程序放在播放器同目录中。"));
        }
    });
    QObject::connect(visibilityAction, &QAction::triggered, &application,
                     [&window, visibilityAction]() {
                         if (window.isVisible()) {
                             window.hide();
                             visibilityAction->setText(QStringLiteral("显示窗口"));
                         } else {
                             window.showWindowAndRaise();
                             visibilityAction->setText(QStringLiteral("隐藏窗口"));
                         }
    });
    QObject::connect(aboutAction, &QAction::triggered, &application, []() {
        QDialog aboutDialog;
        aboutDialog.setWindowTitle(QStringLiteral("软件说明"));
        aboutDialog.setWindowFlag(Qt::WindowStaysOnTopHint);
        aboutDialog.setModal(true);
        aboutDialog.setFixedWidth(1250);

        auto *contentLabel = new QLabel(&aboutDialog);
        contentLabel->setTextFormat(Qt::RichText);
        contentLabel->setWordWrap(true);
        contentLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
        contentLabel->setText(QStringLiteral(
            "<h2>On Screen Music v%1</h2>"
            "<p><b>更新日期：</b>2026-10-16<br>"
            "<b>制作者：</b>ChatGPT &amp; 江沛宸</p>"
            "<p><b>简易用法</b></p>"
            "<ul>"
            "<li>歌词层可播放/暂停、切歌、调节音量、选歌、选歌单和拖动进度。</li>"
            "<li>选歌单后的 ↻× / ↻1 按钮关闭/开启单曲循环；开启后下一首及自然结束均重播当前歌曲。</li>"
            "<li>点击“刷新”可重新读取歌单和当前歌词，不需要重启程序。</li>"
            "<li>未隐藏时，可在任意位置按住鼠标中键拖动窗口。</li>"
            "<li>隐藏后歌词层鼠标穿透；正常模式可按左Ctrl+Num6 恢复，精简模式请从托盘恢复。</li>"
            "<li>歌单、音乐和歌词分别位于软件同目录的 playlists、music、lyrics；从托盘“音乐管理”可处理歌曲、编辑歌词和整理歌单，保存后点击刷新。</li>"
            "<li>LRC 第一行写 #INSTRUMENTAL，或没有有效歌词时，主歌词区显示 _。</li>"
            "</ul>"
            "<p><b>快捷键（NumLock 开关均有效）</b></p>"
            "<ul>"
            "<li>左Ctrl+Num1：回退 5 秒；长按 500 ms 后每 200 ms 重复。</li>"
            "<li>左Ctrl+Num3：快进 5 秒；长按 500 ms 后每 200 ms 重复。</li>"
            "<li>左Ctrl+Num4：下一首；长按 500 ms 后每 700 ms 重复。</li>"
            "<li>左Ctrl+Num5：播放/暂停。</li>"
            "<li>左Ctrl+Num6：隐藏/恢复控件。</li>"
            "</ul>"
            "<p>托盘显示“全部快捷”时五组快捷键均启用；点击后切换为"
            "“播放专用”，此时播放器仅响应左Ctrl+Num5。右Ctrl不参与播放器快捷键，快捷键也不会阻止当前软件同时响应。</p>"
            "<p>Copyright © 2026 Jiang Peichen (Inseven)。项目采用 MIT 许可证。"
            "本软件使用 Qt（Copyright The Qt Company Ltd.），按 LGPLv3 使用；许可文本和对应源码说明见软件目录 ThirdPartyNotices。</p>")
            .arg(QApplication::applicationVersion()));

        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Close, &aboutDialog);
        buttons->button(QDialogButtonBox::Close)->setText(QStringLiteral("关闭"));
        QObject::connect(buttons, &QDialogButtonBox::rejected,
                         &aboutDialog, &QDialog::reject);

        auto *layout = new QVBoxLayout(&aboutDialog);
        layout->setContentsMargins(22, 16, 22, 16);
        layout->setSpacing(12);
        layout->addWidget(contentLabel);
        layout->addWidget(buttons);

        aboutDialog.adjustSize();
        aboutDialog.setFixedWidth(1250);
        aboutDialog.exec();
    });
    QObject::connect(quitAction, &QAction::triggered, &application, &QApplication::quit);
    QObject::connect(&tray, &QSystemTrayIcon::activated, &application,
                     [&window, visibilityAction](QSystemTrayIcon::ActivationReason reason) {
                         if (reason == QSystemTrayIcon::DoubleClick) {
                             window.showWindowAndRaise();
                             visibilityAction->setText(QStringLiteral("隐藏窗口"));
                         }
                     });

    GlobalHotkeyManager hotkeys;
    QObject::connect(playbackOnlyAction, &QAction::triggered,
                     &application, [playbackOnlyAction, &hotkeys]() {
                         const bool enabled = !hotkeys.isPlaybackOnlyMode();
                         hotkeys.setPlaybackOnlyMode(enabled);
                         playbackOnlyAction->setText(
                             enabled ? QStringLiteral("播放专用")
                                     : QStringLiteral("全部快捷"));
                     });
    QObject::connect(&hotkeys, &GlobalHotkeyManager::playPauseRequested,
                     &controller, &PlayerController::togglePlayback);
    QObject::connect(&hotkeys, &GlobalHotkeyManager::nextRequested,
                     &controller, &PlayerController::playRandom);
    QObject::connect(&hotkeys, &GlobalHotkeyManager::lockToggleRequested,
                     &window, &LyricsWindow::toggleLocked);
    QObject::connect(&hotkeys, &GlobalHotkeyManager::seekBackwardRequested,
                     &application, [&controller]() { controller.seekRelative(-5000); });
    QObject::connect(&hotkeys, &GlobalHotkeyManager::seekForwardRequested,
                     &application, [&controller]() { controller.seekRelative(5000); });
    QObject::connect(&application, &QCoreApplication::aboutToQuit,
                     &controller, &PlayerController::savePlaybackState);

    tray.show();
    const QStringList failedHotkeys = hotkeys.registerHotkeys();
    if (!failedHotkeys.isEmpty()) {
        const QString message = QStringLiteral("以下快捷键注册失败：%1")
                                    .arg(failedHotkeys.join(QStringLiteral("、")));
        qWarning().noquote() << message;
        tray.showMessage(QStringLiteral("快捷键初始化失败"), message,
                         QSystemTrayIcon::Warning, 7000);
    }

    window.show();
    controller.start();

    return application.exec();
}

#pragma once

#include <QPoint>
#include <QStringList>
#include <QWidget>


class QFrame;
class QGraphicsOpacityEffect;
class QLabel;
class QLineEdit;
class QListWidget;
class QListWidgetItem;
class QPushButton;
class QSlider;


class LyricsWindow : public QWidget {
    Q_OBJECT

public:
    explicit LyricsWindow(QWidget *parent = nullptr);

    bool isLocked() const;
    void setSongs(const QStringList &titles);
    void setPlaylists(const QStringList &titles, int currentIndex);

public slots:
    void setSingleRepeat(bool enabled);
    void setLyric(const QString &text);
    void setTrack(const QString &title);
    void setPlaybackState(bool playing);
    void setPlaybackPosition(qint64 positionMs, qint64 durationMs);
    void setVolume(int volume);
    void setLocked(bool locked);
    void toggleLocked();
    void showSongSelector();
    void showPlaylistSelector();
    void showWindowAndRaise();

signals:
    void playPauseRequested();
    void nextRequested();
    void seekRequested(qint64 positionMs);
    void volumeRequested(int volume);
    void songRequested(int index);
    void playlistRequested(int index);
    void singleRepeatRequested(bool enabled);
    void refreshRequested();
    void closeRequested();
    void lockedChanged(bool locked);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void showEvent(QShowEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;

private:
    void createSongPopup();
    void createPlaylistPopup();
    void createVolumePopup();
    void moveToInitialPosition();
    void showPopupNearWidget(QWidget *popup, QWidget *anchor);
    void chooseSong(QListWidgetItem *item);
    void choosePlaylist(QListWidgetItem *item);
    void updateTrackLabel();
    void updateLyricFont();
    static QString formatTime(qint64 milliseconds);

    QLabel *m_lyricLabel = nullptr;
    QLabel *m_trackLabel = nullptr;
    QWidget *m_controlPanel = nullptr;
    QGraphicsOpacityEffect *m_controlOpacity = nullptr;
    QPushButton *m_playButton = nullptr;
    QPushButton *m_nextButton = nullptr;
    QPushButton *m_songButton = nullptr;
    QPushButton *m_playlistButton = nullptr;
    QPushButton *m_repeatButton = nullptr;
    QPushButton *m_refreshButton = nullptr;
    QPushButton *m_volumeButton = nullptr;
    QPushButton *m_lockButton = nullptr;
    QPushButton *m_closeButton = nullptr;
    QSlider *m_progressSlider = nullptr;
    QLabel *m_timeLabel = nullptr;

    QFrame *m_songPopup = nullptr;
    QLineEdit *m_songSearch = nullptr;
    QListWidget *m_songList = nullptr;
    QFrame *m_playlistPopup = nullptr;
    QListWidget *m_playlistList = nullptr;
    QFrame *m_volumePopup = nullptr;
    QSlider *m_volumeSlider = nullptr;

    QStringList m_songTitles;
    QStringList m_playlistTitles;
    QString m_trackTitle;
    qint64 m_durationMs = 0;
    QPoint m_dragOffset;
    bool m_locked = false;
    bool m_draggingWindow = false;
    bool m_middleDraggingWindow = false;
    bool m_userSeeking = false;
    bool m_initialPositionApplied = false;
};

#pragma once

#include "lrc_parser.h"

#include <QMediaPlayer>
#include <QObject>
#include <QSet>
#include <QStringList>
#include <QTimer>
#include <QVector>


struct Song {
    QString title;
    QString audioPath;
    QString lyricPath;
    int weight = 1;
};


struct Playlist {
    QString title;
    QString fileName;
    QString filePath;
};


class PlayerController : public QObject {
    Q_OBJECT

public:
    explicit PlayerController(QObject *parent = nullptr);

    void start();
    const QVector<Song> &songs() const;
    const QVector<Playlist> &playlists() const;
    QString libraryRoot() const;
    QString defaultLibraryRoot() const;

public slots:
    void playRandom();
    void setSingleRepeat(bool enabled);
    void playSong(int index);
    void selectPlaylist(int index);
    void refreshLibrary();
    void togglePlayback();
    void seek(qint64 positionMs);
    void seekRelative(qint64 offsetMs);
    void setVolume(int volume);
    void adjustVolume(int delta);
    void savePlaybackState();

signals:
    void singleRepeatChanged(bool enabled);
    void lyricChanged(const QString &text);
    void trackChanged(const QString &title);
    void playbackChanged(bool playing);
    void playbackPositionChanged(qint64 positionMs, qint64 durationMs);
    void volumeChanged(int volume);
    void songsChanged(const QStringList &titles);
    void playlistsChanged(const QStringList &titles, int currentIndex);
    void playlistLoadWarnings(const QString &playlistName,
                              const QStringList &warnings,
                              int loadedSongCount);
    void errorMessage(const QString &message);

private slots:
    void handlePositionChanged(qint64 positionMs);
    void handleDurationChanged(qint64 durationMs);
    void handleMediaStatusChanged(QMediaPlayer::MediaStatus status);
    void handlePlayerError(QMediaPlayer::Error error);

private:
    void scanPlaylists();
    void loadPlaylist(int index);
    void scanLibrary(const QString &playlistPath);
    void beginSong(int index, bool resetFailures, bool playImmediately,
                   qint64 initialPositionMs = 0);
    void applyPendingPosition();
    void syncPlaybackProgress();
    void updateDisplayedLyric(qint64 positionMs);
    void scheduleFailureRecovery();
    int randomIndex() const;
    int randomIndexExcludingFailures() const;

    QMediaPlayer m_player;
    QTimer m_progressTimer;
    QTimer m_stateSaveTimer;
    QVector<Song> m_songs;
    QVector<Playlist> m_playlists;
    QVector<LrcLine> m_lyrics;
    QSet<int> m_failedSongs;
    QString m_libraryRoot;
    QString m_libraryMessage = QStringLiteral("播放列表中没有可播放的歌曲");
    int m_currentIndex = -1;
    int m_currentPlaylistIndex = -1;
    qint64 m_durationMs = 0;
    qint64 m_pendingPositionMs = -1;
    QString m_lastDisplayedText;
    bool m_hasDisplayedText = false;
    bool m_failureRecoveryScheduled = false;
    bool m_playImmediately = false;
    bool m_instrumental = false;
    bool m_singleRepeat = false;
};

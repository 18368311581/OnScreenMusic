#include "player_controller.h"

#include "app_settings.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QRandomGenerator>
#include <QTextCodec>
#include <QTimer>
#include <QUrl>


namespace {

constexpr int MaximumVolume = 20;
constexpr qint64 LyricDisplayDurationMs = 5000;

bool isPlainFileName(const QString &name)
{
    return !name.isEmpty()
        && name != QStringLiteral(".")
        && name != QStringLiteral("..")
        && !name.contains(QLatin1Char('/'))
        && !name.contains(QLatin1Char('\\'));
}

}


PlayerController::PlayerController(QObject *parent)
    : QObject(parent)
{
    m_libraryRoot = defaultLibraryRoot();
    const AppSettings settings;
    m_singleRepeat = settings.value(QStringLiteral("Playback/SingleRepeat"), false).toBool();
    m_player.setVolume(qBound(
        0, settings.value(QStringLiteral("Audio/Volume"), 14).toInt(), MaximumVolume));
    m_player.setNotifyInterval(250);

    m_progressTimer.setInterval(250);
    m_stateSaveTimer.setInterval(2000);

    connect(&m_player, &QMediaPlayer::positionChanged,
            this, &PlayerController::handlePositionChanged);
    connect(&m_player, &QMediaPlayer::durationChanged,
            this, &PlayerController::handleDurationChanged);
    connect(&m_player, &QMediaPlayer::mediaStatusChanged,
            this, &PlayerController::handleMediaStatusChanged);
    connect(&m_player, &QMediaPlayer::stateChanged, this,
            [this](QMediaPlayer::State state) {
                emit playbackChanged(state == QMediaPlayer::PlayingState);
                if (state != QMediaPlayer::PlayingState) {
                    savePlaybackState();
                }
            });
    connect(&m_player, QOverload<QMediaPlayer::Error>::of(&QMediaPlayer::error),
            this, &PlayerController::handlePlayerError);
    connect(&m_progressTimer, &QTimer::timeout,
            this, &PlayerController::syncPlaybackProgress);
    connect(&m_stateSaveTimer, &QTimer::timeout, this, [this]() {
        if (m_player.state() == QMediaPlayer::PlayingState) {
            savePlaybackState();
        }
    });

    m_progressTimer.start();
    m_stateSaveTimer.start();
}


void PlayerController::start()
{
    emit singleRepeatChanged(m_singleRepeat);
    scanPlaylists();
    emit volumeChanged(m_player.volume());
    if (m_playlists.isEmpty()) {
        emit playlistsChanged(QStringList(), -1);
        emit songsChanged(QStringList());
        emit trackChanged(QString());
        emit lyricChanged(QStringLiteral("没有可用的歌单"));
        return;
    }

    const AppSettings settings;
    const QString savedPlaylist =
        settings.value(QStringLiteral("Library/PlaylistFile")).toString();
    m_currentPlaylistIndex = 0;
    for (int index = 0; index < m_playlists.size(); ++index) {
        if (m_playlists.at(index).fileName.compare(savedPlaylist, Qt::CaseInsensitive) == 0) {
            m_currentPlaylistIndex = index;
            break;
        }
    }
    loadPlaylist(m_currentPlaylistIndex);

    if (m_songs.isEmpty()) {
        emit trackChanged(QString());
        emit lyricChanged(m_libraryMessage);
        return;
    }

    int songIndex = -1;
    qint64 savedPositionMs = 0;
    const bool restoredPlaylist = !savedPlaylist.isEmpty()
        && m_playlists.at(m_currentPlaylistIndex).fileName.compare(
               savedPlaylist, Qt::CaseInsensitive) == 0;
    if (restoredPlaylist) {
        const QString savedAudio =
            settings.value(QStringLiteral("Playback/AudioFile")).toString();
        for (int index = 0; index < m_songs.size(); ++index) {
            if (QFileInfo(m_songs.at(index).audioPath).fileName().compare(
                    savedAudio, Qt::CaseInsensitive) == 0) {
                songIndex = index;
                savedPositionMs = qMax<qint64>(
                    0, settings.value(QStringLiteral("Playback/PositionMs"), 0).toLongLong());
                break;
            }
        }
    }
    if (songIndex < 0) {
        songIndex = randomIndex();
    }
    beginSong(songIndex, true, false, savedPositionMs);
}


const QVector<Song> &PlayerController::songs() const
{
    return m_songs;
}


const QVector<Playlist> &PlayerController::playlists() const
{
    return m_playlists;
}


QString PlayerController::libraryRoot() const
{
    return m_libraryRoot;
}


QString PlayerController::defaultLibraryRoot() const
{
    return QDir::cleanPath(QCoreApplication::applicationDirPath());
}


void PlayerController::scanPlaylists()
{
    m_playlists.clear();
    const QDir rootDirectory(m_libraryRoot);
    const QDir playlistDirectory(rootDirectory.filePath(QStringLiteral("playlists")));
    const QFileInfoList playlistFiles = playlistDirectory.entryInfoList(
        QStringList() << QStringLiteral("*.txt"),
        QDir::Files | QDir::Readable | QDir::NoSymLinks,
        QDir::Name | QDir::IgnoreCase);
    for (const QFileInfo &file : playlistFiles) {
        m_playlists.append({file.completeBaseName(), file.fileName(), file.absoluteFilePath()});
    }

    if (m_playlists.isEmpty()) {
        const QFileInfo legacyPlaylist(
            rootDirectory.filePath(QStringLiteral("playlist.txt")));
        if (legacyPlaylist.isFile() && legacyPlaylist.isReadable()) {
            m_playlists.append({QStringLiteral("playlist（旧版）"),
                                legacyPlaylist.fileName(),
                                legacyPlaylist.absoluteFilePath()});
        }
    }
}


void PlayerController::loadPlaylist(int index)
{
    if (index < 0 || index >= m_playlists.size()) {
        return;
    }
    m_currentPlaylistIndex = index;
    scanLibrary(m_playlists.at(index).filePath);

    QStringList playlistTitles;
    playlistTitles.reserve(m_playlists.size());
    for (const Playlist &playlist : m_playlists) {
        playlistTitles.append(playlist.title);
    }
    emit playlistsChanged(playlistTitles, m_currentPlaylistIndex);

    QStringList songTitles;
    songTitles.reserve(m_songs.size());
    for (const Song &song : m_songs) {
        songTitles.append(song.title);
    }
    emit songsChanged(songTitles);
    AppSettings().setValue(QStringLiteral("Library/PlaylistFile"),
                           m_playlists.at(index).fileName);
}


void PlayerController::scanLibrary(const QString &playlistPath)
{
    m_songs.clear();
    m_libraryMessage = QStringLiteral("播放列表中没有可播放的歌曲");

    const QDir rootDirectory(m_libraryRoot);
    const QDir musicDirectory(rootDirectory.filePath(QStringLiteral("music")));
    const QDir lyricsDirectory(rootDirectory.filePath(QStringLiteral("lyrics")));
    QFile playlist(playlistPath);
    const QString playlistName = QFileInfo(playlistPath).fileName();
    QStringList warnings;
    const auto addWarning = [&warnings](const QString &message) {
        warnings.append(message);
        qWarning().noquote() << message;
    };
    const auto reportWarnings = [this, &playlistName, &warnings]() {
        if (!warnings.isEmpty()) {
            emit playlistLoadWarnings(playlistName, warnings, m_songs.size());
        }
    };
    if (!playlist.exists()) {
        m_libraryMessage = QStringLiteral("找不到歌单：%1").arg(playlistName);
        addWarning(m_libraryMessage);
        reportWarnings();
        return;
    }
    if (!playlist.open(QIODevice::ReadOnly)) {
        m_libraryMessage = QStringLiteral("无法读取歌单：%1").arg(playlistName);
        addWarning(QStringLiteral("%1（%2）")
                       .arg(m_libraryMessage, playlist.errorString()));
        reportWarnings();
        return;
    }

    QTextCodec::ConverterState decoderState;
    const QByteArray playlistBytes = playlist.readAll();
    QString playlistText = QTextCodec::codecForName("UTF-8")->toUnicode(
        playlistBytes.constData(), playlistBytes.size(), &decoderState);
    if (decoderState.invalidChars > 0) {
        m_libraryMessage = QStringLiteral("歌单不是有效的 UTF-8 文件：%1").arg(playlistName);
        addWarning(m_libraryMessage);
        reportWarnings();
        return;
    }
    if (!playlistText.isEmpty() && playlistText.front() == QChar::ByteOrderMark) {
        playlistText.remove(0, 1);
    }

    QHash<QString, int> songIndexByAudio;
    QHash<QString, QString> lyricConfigByAudio;
    const QStringList lines = playlistText.split(QLatin1Char('\n'));
    for (int index = 0; index < lines.size(); ++index) {
        const int lineNumber = index + 1;
        const QString line = lines.at(index).trimmed();
        if (line.isEmpty() || line.startsWith(QLatin1Char('#'))) {
            continue;
        }

        const QStringList fields = line.split(QLatin1Char('|'));
        if (fields.size() != 2) {
            addWarning(QStringLiteral("%1 第 %2 行格式错误，已跳过")
                           .arg(playlistName).arg(lineNumber));
            continue;
        }

        const QString audioName = fields.at(0).trimmed();
        const QString lyricName = fields.at(1).trimmed();
        if (!isPlainFileName(audioName)
            || !audioName.endsWith(QStringLiteral(".mp3"), Qt::CaseInsensitive)) {
            addWarning(QStringLiteral("%1 第 %2 行的音乐文件名无效，已跳过")
                           .arg(playlistName).arg(lineNumber));
            continue;
        }

        const QFileInfo audioFile(musicDirectory.filePath(audioName));
        if (!audioFile.isFile() || !audioFile.isReadable()) {
            addWarning(QStringLiteral("%1 第 %2 行找不到音乐：%3")
                           .arg(playlistName).arg(lineNumber).arg(audioName));
            continue;
        }

        const QString audioKey = audioName.toCaseFolded();
        const QString lyricConfig = lyricName == QStringLiteral("-")
            ? QStringLiteral("-") : lyricName.toCaseFolded();
        const auto existingSong = songIndexByAudio.constFind(audioKey);
        if (existingSong != songIndexByAudio.constEnd()) {
            if (lyricConfigByAudio.value(audioKey) != lyricConfig) {
                addWarning(QStringLiteral(
                               "%1 第 %2 行重复音乐的歌词配置不一致，未增加权重")
                               .arg(playlistName).arg(lineNumber));
            } else {
                ++m_songs[existingSong.value()].weight;
            }
            continue;
        }

        QString lyricPath;
        if (lyricName != QStringLiteral("-")) {
            if (!isPlainFileName(lyricName)
                || !lyricName.endsWith(QStringLiteral(".lrc"), Qt::CaseInsensitive)) {
                addWarning(QStringLiteral("%1 第 %2 行的歌词文件名无效，将显示 _")
                               .arg(playlistName).arg(lineNumber));
            } else {
                const QFileInfo lyricFile(lyricsDirectory.filePath(lyricName));
                if (lyricFile.isFile() && lyricFile.isReadable()) {
                    lyricPath = lyricFile.absoluteFilePath();
                } else {
                    addWarning(QStringLiteral("%1 第 %2 行找不到歌词：%3，将显示 _")
                                   .arg(playlistName).arg(lineNumber).arg(lyricName));
                }
            }
        }

        songIndexByAudio.insert(audioKey, m_songs.size());
        lyricConfigByAudio.insert(audioKey, lyricConfig);
        m_songs.append(
            {audioFile.completeBaseName(), audioFile.absoluteFilePath(), lyricPath, 1});
    }
    if (m_songs.isEmpty()) {
        m_libraryMessage = QStringLiteral("歌单中没有可播放的歌曲：%1").arg(playlistName);
    }
    qInfo().noquote()
        << QStringLiteral("已从 %1 加载 %2 首歌曲").arg(playlistName).arg(m_songs.size());
    reportWarnings();
}


void PlayerController::playRandom()
{
    if (m_songs.isEmpty()) {
        return;
    }
    savePlaybackState();
    const bool repeatCurrent = m_singleRepeat && m_currentIndex >= 0
        && m_currentIndex < m_songs.size();
    const int index = repeatCurrent ? m_currentIndex : randomIndex();
    if (repeatCurrent) {
        m_player.stop();
        m_player.setPosition(0);
    }
    beginSong(index, true, true);
}


void PlayerController::setSingleRepeat(bool enabled)
{
    m_singleRepeat = enabled;
    AppSettings().setValue(QStringLiteral("Playback/SingleRepeat"), enabled);
    emit singleRepeatChanged(enabled);
}


void PlayerController::playSong(int index)
{
    if (index < 0 || index >= m_songs.size()) {
        return;
    }
    savePlaybackState();
    beginSong(index, true, true);
}


void PlayerController::selectPlaylist(int index)
{
    if (index < 0 || index >= m_playlists.size() || index == m_currentPlaylistIndex) {
        return;
    }
    savePlaybackState();
    m_playImmediately = false;
    m_player.stop();
    m_currentIndex = -1;
    m_pendingPositionMs = -1;
    loadPlaylist(index);
    if (m_songs.isEmpty()) {
        AppSettings settings;
        settings.remove(QStringLiteral("Playback/AudioFile"));
        settings.remove(QStringLiteral("Playback/PositionMs"));
        emit trackChanged(QString());
        emit playbackPositionChanged(0, 0);
        emit playbackChanged(false);
        emit lyricChanged(m_libraryMessage);
        return;
    }
    const int songIndex = randomIndex();
    beginSong(songIndex, true, false);
}


void PlayerController::refreshLibrary()
{
    savePlaybackState();
    const bool wasPlaying = m_player.state() == QMediaPlayer::PlayingState;
    const qint64 currentPositionMs = m_pendingPositionMs >= 0
        ? m_pendingPositionMs : m_player.position();
    const QString currentPlaylistFile =
        m_currentPlaylistIndex >= 0 && m_currentPlaylistIndex < m_playlists.size()
            ? m_playlists.at(m_currentPlaylistIndex).fileName
            : QString();
    const QString currentAudioFile =
        m_currentIndex >= 0 && m_currentIndex < m_songs.size()
            ? QFileInfo(m_songs.at(m_currentIndex).audioPath).fileName()
            : QString();

    m_currentIndex = -1;
    scanPlaylists();
    if (m_playlists.isEmpty()) {
        m_playImmediately = false;
        m_player.stop();
        m_songs.clear();
        m_lyrics.clear();
        m_currentPlaylistIndex = -1;
        m_durationMs = 0;
        m_pendingPositionMs = -1;
        emit playlistsChanged(QStringList(), -1);
        emit songsChanged(QStringList());
        emit trackChanged(QString());
        emit playbackPositionChanged(0, 0);
        emit playbackChanged(false);
        emit lyricChanged(QStringLiteral("没有可用的歌单"));
        AppSettings settings;
        settings.remove(QStringLiteral("Library/PlaylistFile"));
        settings.remove(QStringLiteral("Playback/AudioFile"));
        settings.remove(QStringLiteral("Playback/PositionMs"));
        return;
    }

    int playlistIndex = 0;
    for (int index = 0; index < m_playlists.size(); ++index) {
        if (m_playlists.at(index).fileName.compare(
                currentPlaylistFile, Qt::CaseInsensitive) == 0) {
            playlistIndex = index;
            break;
        }
    }
    loadPlaylist(playlistIndex);

    int songIndex = -1;
    for (int index = 0; index < m_songs.size(); ++index) {
        if (QFileInfo(m_songs.at(index).audioPath).fileName().compare(
                currentAudioFile, Qt::CaseInsensitive) == 0) {
            songIndex = index;
            break;
        }
    }

    if (songIndex >= 0) {
        m_currentIndex = songIndex;
        m_failedSongs.clear();
        m_failureRecoveryScheduled = false;
        m_playImmediately = wasPlaying;
        m_instrumental = false;
        const Song &song = m_songs.at(songIndex);
        m_lyrics = song.lyricPath.isEmpty()
            ? QVector<LrcLine>()
            : LrcParser::parseFile(song.lyricPath, &m_instrumental);
        m_lastDisplayedText.clear();
        m_hasDisplayedText = false;
        emit trackChanged(song.title);
        updateDisplayedLyric(currentPositionMs);
        emit playbackPositionChanged(currentPositionMs, m_durationMs);
        emit playbackChanged(wasPlaying);
        savePlaybackState();
        return;
    }

    m_playImmediately = false;
    m_player.stop();
    m_durationMs = 0;
    m_pendingPositionMs = -1;
    if (m_songs.isEmpty()) {
        m_lyrics.clear();
        emit trackChanged(QString());
        emit playbackPositionChanged(0, 0);
        emit playbackChanged(false);
        emit lyricChanged(m_libraryMessage);
        AppSettings settings;
        settings.remove(QStringLiteral("Playback/AudioFile"));
        settings.remove(QStringLiteral("Playback/PositionMs"));
        return;
    }

    beginSong(randomIndex(), true, false);
}


void PlayerController::beginSong(
    int index, bool resetFailures, bool playImmediately, qint64 initialPositionMs)
{
    if (resetFailures) {
        m_failedSongs.clear();
    }
    m_failureRecoveryScheduled = false;
    m_currentIndex = index;
    m_durationMs = 0;
    m_pendingPositionMs = initialPositionMs > 0 ? initialPositionMs : -1;
    m_lastDisplayedText.clear();
    m_hasDisplayedText = false;
    m_playImmediately = playImmediately;

    const Song &song = m_songs.at(index);
    m_instrumental = false;
    m_lyrics = song.lyricPath.isEmpty()
        ? QVector<LrcLine>()
        : LrcParser::parseFile(song.lyricPath, &m_instrumental);
    emit trackChanged(song.title);
    emit playbackPositionChanged(qMax<qint64>(0, initialPositionMs), 0);
    updateDisplayedLyric(qMax<qint64>(0, initialPositionMs));

    m_player.setMedia(QUrl::fromLocalFile(song.audioPath));
    if (playImmediately) {
        m_player.play();
    } else {
        emit playbackChanged(false);
    }
    savePlaybackState();
}


void PlayerController::togglePlayback()
{
    if (m_player.state() == QMediaPlayer::PlayingState) {
        m_playImmediately = false;
        m_player.pause();
    } else if (m_currentIndex >= 0) {
        m_playImmediately = true;
        m_player.play();
    } else {
        playRandom();
    }
}


void PlayerController::seek(qint64 positionMs)
{
    if (m_currentIndex < 0) {
        return;
    }
    m_pendingPositionMs = -1;
    const qint64 maximum = m_durationMs > 0 ? m_durationMs : qMax<qint64>(0, positionMs);
    m_player.setPosition(qBound<qint64>(0, positionMs, maximum));
    syncPlaybackProgress();
    savePlaybackState();
}


void PlayerController::seekRelative(qint64 offsetMs)
{
    if (m_currentIndex < 0) {
        return;
    }
    const qint64 durationMs = qMax(m_durationMs, m_player.duration());
    if (offsetMs > 0 && durationMs <= 0) {
        return;
    }
    const qint64 maximum = durationMs > 0 ? durationMs : m_player.position();
    seek(qBound<qint64>(0, m_player.position() + offsetMs, maximum));
}


void PlayerController::setVolume(int volume)
{
    m_player.setVolume(qBound(0, volume, MaximumVolume));
    AppSettings().setValue(QStringLiteral("Audio/Volume"), m_player.volume());
    emit volumeChanged(m_player.volume());
}


void PlayerController::adjustVolume(int delta)
{
    setVolume(m_player.volume() + delta);
}


void PlayerController::savePlaybackState()
{
    AppSettings settings;
    settings.setValue(QStringLiteral("Audio/Volume"), m_player.volume());
    if (m_currentPlaylistIndex >= 0 && m_currentPlaylistIndex < m_playlists.size()) {
        settings.setValue(QStringLiteral("Library/PlaylistFile"),
                          m_playlists.at(m_currentPlaylistIndex).fileName);
    }
    if (m_currentIndex >= 0 && m_currentIndex < m_songs.size()) {
        settings.setValue(QStringLiteral("Playback/AudioFile"),
                          QFileInfo(m_songs.at(m_currentIndex).audioPath).fileName());
        settings.setValue(QStringLiteral("Playback/PositionMs"),
                          m_pendingPositionMs >= 0 ? m_pendingPositionMs
                                                   : m_player.position());
    }
}


void PlayerController::handlePositionChanged(qint64 positionMs)
{
    const qint64 effectivePosition = m_pendingPositionMs >= 0
        ? m_pendingPositionMs : positionMs;
    updateDisplayedLyric(effectivePosition);
    emit playbackPositionChanged(effectivePosition, m_durationMs);
}


void PlayerController::handleDurationChanged(qint64 durationMs)
{
    m_durationMs = qMax<qint64>(0, durationMs);
    applyPendingPosition();
    emit playbackPositionChanged(
        m_pendingPositionMs >= 0 ? m_pendingPositionMs : m_player.position(),
        m_durationMs);
}


void PlayerController::handleMediaStatusChanged(QMediaPlayer::MediaStatus status)
{
    if (status == QMediaPlayer::LoadedMedia || status == QMediaPlayer::BufferedMedia) {
        applyPendingPosition();
        syncPlaybackProgress();
    }
    if (status == QMediaPlayer::EndOfMedia) {
        playRandom();
    }
}


void PlayerController::applyPendingPosition()
{
    if (m_pendingPositionMs < 0) {
        return;
    }
    const qint64 durationMs = qMax(m_durationMs, m_player.duration());
    if (durationMs <= 0) {
        return;
    }
    m_durationMs = durationMs;
    const qint64 targetPosition = qBound<qint64>(0, m_pendingPositionMs, durationMs);
    m_pendingPositionMs = -1;
    m_player.setPosition(targetPosition);
}


void PlayerController::syncPlaybackProgress()
{
    if (m_currentIndex < 0) {
        return;
    }
    const qint64 reportedDuration = m_player.duration();
    if (reportedDuration > 0) {
        m_durationMs = reportedDuration;
    }
    applyPendingPosition();
    const qint64 positionMs = m_pendingPositionMs >= 0
        ? m_pendingPositionMs : m_player.position();
    updateDisplayedLyric(positionMs);
    emit playbackPositionChanged(positionMs, m_durationMs);
}


void PlayerController::handlePlayerError(QMediaPlayer::Error error)
{
    if (error == QMediaPlayer::NoError || m_currentIndex < 0) {
        return;
    }
    scheduleFailureRecovery();
}


void PlayerController::updateDisplayedLyric(qint64 positionMs)
{
    if (m_currentIndex < 0) {
        return;
    }

    QString displayText = QStringLiteral("_");
    QString lyricText;
    if (!m_instrumental
        && LrcParser::textAt(
            m_lyrics, positionMs, &lyricText, LyricDisplayDurationMs)) {
        if (!lyricText.isEmpty()) {
            displayText = lyricText;
        }
    }
    if (m_hasDisplayedText && displayText == m_lastDisplayedText) {
        return;
    }
    m_lastDisplayedText = displayText;
    m_hasDisplayedText = true;
    emit lyricChanged(displayText);
}


void PlayerController::scheduleFailureRecovery()
{
    if (m_failureRecoveryScheduled) {
        return;
    }
    m_failureRecoveryScheduled = true;
    const int failedIndex = m_currentIndex;
    const bool playAfterRecovery = m_playImmediately;
    const QString failureText = m_player.errorString().isEmpty()
        ? QStringLiteral("未知播放错误")
        : m_player.errorString();

    QTimer::singleShot(0, this, [this, failedIndex, failureText, playAfterRecovery]() {
        if (!m_failureRecoveryScheduled) {
            return;
        }
        m_failureRecoveryScheduled = false;
        if (failedIndex >= 0) {
            m_failedSongs.insert(failedIndex);
        }
        emit errorMessage(QStringLiteral("播放失败：%1").arg(failureText));

        const int nextIndex = randomIndexExcludingFailures();
        if (nextIndex < 0) {
            m_player.stop();
            emit lyricChanged(QStringLiteral("所有歌曲均无法播放"));
            return;
        }
        beginSong(nextIndex, false, playAfterRecovery);
    });
}


int PlayerController::randomIndex() const
{
    int totalWeight = 0;
    for (const Song &song : m_songs) {
        totalWeight += song.weight;
    }
    if (totalWeight <= 0) {
        return -1;
    }

    int draw = QRandomGenerator::global()->bounded(totalWeight);
    for (int index = 0; index < m_songs.size(); ++index) {
        draw -= m_songs.at(index).weight;
        if (draw < 0) {
            return index;
        }
    }
    return -1;
}


int PlayerController::randomIndexExcludingFailures() const
{
    int totalWeight = 0;
    for (int index = 0; index < m_songs.size(); ++index) {
        if (!m_failedSongs.contains(index)) {
            totalWeight += m_songs.at(index).weight;
        }
    }
    if (totalWeight <= 0) {
        return -1;
    }

    int draw = QRandomGenerator::global()->bounded(totalWeight);
    for (int index = 0; index < m_songs.size(); ++index) {
        if (m_failedSongs.contains(index)) {
            continue;
        }
        draw -= m_songs.at(index).weight;
        if (draw < 0) {
            return index;
        }
    }
    return -1;
}

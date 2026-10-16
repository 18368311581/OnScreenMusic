#include "lyrics_window.h"

#include "app_settings.h"

#include <QApplication>
#include <QEvent>
#include <QFont>
#include <QFontMetrics>
#include <QFrame>
#include <QGraphicsDropShadowEffect>
#include <QGraphicsOpacityEffect>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMouseEvent>
#include <QPushButton>
#include <QResizeEvent>
#include <QScreen>
#include <QShowEvent>
#include <QSignalBlocker>
#include <QSizePolicy>
#include <QSlider>
#include <QStyle>
#include <QStyleOptionSlider>
#include <QVBoxLayout>

#include <algorithm>
#include <climits>


namespace {

class SeekSlider final : public QSlider {
public:
    using QSlider::QSlider;

protected:
    void mousePressEvent(QMouseEvent *event) override
    {
        if (event->button() == Qt::LeftButton && maximum() > minimum()) {
            QStyleOptionSlider option;
            initStyleOption(&option);
            const QRect groove = style()->subControlRect(
                QStyle::CC_Slider, &option, QStyle::SC_SliderGroove, this);
            const QRect handle = style()->subControlRect(
                QStyle::CC_Slider, &option, QStyle::SC_SliderHandle, this);
            const int sliderMinimum = groove.x();
            const int sliderMaximum = groove.right() - handle.width() + 1;
            const int position = event->pos().x() - sliderMinimum - handle.width() / 2;
            setValue(QStyle::sliderValueFromPosition(
                minimum(), maximum(), position,
                qMax(0, sliderMaximum - sliderMinimum), option.upsideDown));
        }
        QSlider::mousePressEvent(event);
    }
};

}


LyricsWindow::LyricsWindow(QWidget *parent)
    : QWidget(parent)
{
    setWindowTitle(QStringLiteral("On Screen Music"));
    setWindowFlags(Qt::Tool | Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    setAttribute(Qt::WA_TranslucentBackground);
    resize(900, 238);

    m_lyricLabel = new QLabel(QStringLiteral("正在读取播放列表……"), this);
    m_lyricLabel->setAlignment(Qt::AlignHCenter | Qt::AlignBottom);
    m_lyricLabel->setWordWrap(false);
    m_lyricLabel->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    m_lyricLabel->setContentsMargins(8, 0, 8, 0);
    m_lyricLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_lyricLabel->setStyleSheet(QStringLiteral("color: white; background: transparent;"));

    QFont lyricFont(QStringLiteral("Microsoft YaHei UI"));
    lyricFont.setPixelSize(60);
    lyricFont.setBold(true);
    m_lyricLabel->setFont(lyricFont);

    auto *shadow = new QGraphicsDropShadowEffect(m_lyricLabel);
    shadow->setBlurRadius(8);
    shadow->setColor(QColor(0, 0, 0, 230));
    shadow->setOffset(2, 2);
    m_lyricLabel->setGraphicsEffect(shadow);

    m_controlPanel = new QWidget(this);
    m_controlPanel->setObjectName(QStringLiteral("controlPanel"));
    m_playButton = new QPushButton(QStringLiteral("▶"), m_controlPanel);
    m_nextButton = new QPushButton(QStringLiteral("⏭"), m_controlPanel);
    m_songButton = new QPushButton(QStringLiteral("选歌"), m_controlPanel);
    m_playlistButton = new QPushButton(QStringLiteral("选歌单"), m_controlPanel);
    m_repeatButton = new QPushButton(QStringLiteral("↻×"), m_controlPanel);
    m_repeatButton->setCheckable(true);
    m_refreshButton = new QPushButton(QStringLiteral("刷新"), m_controlPanel);
    m_volumeButton = new QPushButton(QStringLiteral("🔊"), m_controlPanel);
    m_lockButton = new QPushButton(QStringLiteral("隐藏"), m_controlPanel);
    m_closeButton = new QPushButton(QStringLiteral("关闭"), m_controlPanel);
    m_playButton->setToolTip(QStringLiteral("播放/暂停"));
    m_nextButton->setToolTip(QStringLiteral("下一首"));
    m_volumeButton->setToolTip(QStringLiteral("音量"));
    m_songButton->setToolTip(QStringLiteral("选择歌曲"));
    m_playlistButton->setToolTip(QStringLiteral("选择歌单"));
    m_repeatButton->setToolTip(QStringLiteral("单曲循环已关闭，点击开启"));
    m_refreshButton->setToolTip(QStringLiteral("重新读取歌单和歌词"));
    m_lockButton->setToolTip(QStringLiteral("隐藏控件并启用鼠标穿透"));
    m_closeButton->setToolTip(QStringLiteral("退出程序"));

    QFont mediaFont(QStringLiteral("Segoe UI Symbol"));
    mediaFont.setPixelSize(26);
    m_playButton->setFont(mediaFont);
    m_nextButton->setFont(mediaFont);
    m_repeatButton->setFont(mediaFont);
    QFont volumeFont(QStringLiteral("Segoe UI Emoji"));
    volumeFont.setPixelSize(25);
    m_volumeButton->setFont(volumeFont);

    const QSize controlButtonSize(84, 42);
    m_playButton->setFixedSize(controlButtonSize);
    m_nextButton->setFixedSize(controlButtonSize);
    m_volumeButton->setFixedSize(controlButtonSize);
    m_songButton->setFixedSize(controlButtonSize);
    m_playlistButton->setFixedSize(controlButtonSize);
    m_repeatButton->setFixedSize(controlButtonSize);
    m_refreshButton->setFixedSize(controlButtonSize);
    m_lockButton->setFixedSize(controlButtonSize);
    m_closeButton->setFixedSize(controlButtonSize);
    m_progressSlider = new SeekSlider(Qt::Horizontal, m_controlPanel);
    m_progressSlider->setFocusPolicy(Qt::NoFocus);
    m_progressSlider->setMinimumHeight(26);
    m_progressSlider->setRange(0, 0);
    m_trackLabel = new QLabel(m_controlPanel);
    m_trackLabel->setFixedWidth(190);
    m_trackLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_timeLabel = new QLabel(QStringLiteral("00:00 / 00:00"), m_controlPanel);
    m_timeLabel->setMinimumWidth(92);
    m_timeLabel->setAlignment(Qt::AlignCenter);

    auto *progressLayout = new QHBoxLayout;
    progressLayout->setContentsMargins(0, 0, 0, 0);
    progressLayout->setSpacing(8);
    progressLayout->addWidget(m_trackLabel);
    progressLayout->addWidget(m_progressSlider, 1);
    progressLayout->addWidget(m_timeLabel);

    auto *buttonLayout = new QHBoxLayout;
    buttonLayout->setContentsMargins(0, 0, 0, 0);
    buttonLayout->setSpacing(7);
    buttonLayout->addStretch();
    buttonLayout->addWidget(m_playButton);
    buttonLayout->addWidget(m_nextButton);
    buttonLayout->addWidget(m_volumeButton);
    buttonLayout->addWidget(m_songButton);
    buttonLayout->addWidget(m_playlistButton);
    buttonLayout->addWidget(m_repeatButton);
    buttonLayout->addWidget(m_refreshButton);
    buttonLayout->addWidget(m_lockButton);
    buttonLayout->addWidget(m_closeButton);
    buttonLayout->addStretch();

    auto *controlLayout = new QVBoxLayout(m_controlPanel);
    controlLayout->setContentsMargins(14, 8, 14, 8);
    controlLayout->setSpacing(5);
    controlLayout->addLayout(progressLayout);
    controlLayout->addLayout(buttonLayout);

    m_controlOpacity = new QGraphicsOpacityEffect(m_controlPanel);
    m_controlOpacity->setOpacity(1.0);
    m_controlPanel->setGraphicsEffect(m_controlOpacity);

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(24, 8, 24, 8);
    layout->setSpacing(0);
    layout->addWidget(m_lyricLabel, 1);
    layout->addWidget(m_controlPanel);

    setStyleSheet(QStringLiteral(R"(
        QWidget#controlPanel {
            background: rgba(10, 10, 10, 92);
            border-radius: 11px;
        }
        QWidget#controlPanel QPushButton {
            color: rgba(255, 255, 255, 185);
            background: rgba(255, 255, 255, 24);
            border: 1px solid rgba(255, 255, 255, 35);
            border-radius: 7px;
            min-width: 64px;
            padding: 4px 9px;
        }
        QWidget#controlPanel QPushButton:hover {
            color: white;
            background: rgba(255, 255, 255, 70);
            border-color: rgba(255, 255, 255, 105);
        }
        QWidget#controlPanel QPushButton:pressed {
            background: rgba(255, 255, 255, 105);
        }
        QWidget#controlPanel QLabel { color: rgba(255, 255, 255, 190); }
        QSlider::groove:horizontal {
            height: 8px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 55);
        }
        QSlider::sub-page:horizontal {
            border-radius: 4px;
            background: rgba(255, 255, 255, 175);
        }
        QSlider::handle:horizontal {
            width: 18px;
            margin: -5px 0;
            border-radius: 9px;
            background: white;
        }
    )"));

    createSongPopup();
    createPlaylistPopup();
    createVolumePopup();

    connect(m_playButton, &QPushButton::clicked, this, &LyricsWindow::playPauseRequested);
    connect(m_nextButton, &QPushButton::clicked, this, &LyricsWindow::nextRequested);
    connect(m_songButton, &QPushButton::clicked, this, &LyricsWindow::showSongSelector);
    connect(m_playlistButton, &QPushButton::clicked,
            this, &LyricsWindow::showPlaylistSelector);
    connect(m_repeatButton, &QPushButton::toggled, this, [this](bool enabled) {
        setSingleRepeat(enabled);
        emit singleRepeatRequested(enabled);
    });
    connect(m_refreshButton, &QPushButton::clicked,
            this, &LyricsWindow::refreshRequested);
    connect(m_volumeButton, &QPushButton::clicked, this, [this]() {
        showPopupNearWidget(m_volumePopup, m_volumeButton);
    });
    connect(m_lockButton, &QPushButton::clicked, this, [this]() { setLocked(true); });
    connect(m_closeButton, &QPushButton::clicked, this, &LyricsWindow::closeRequested);

    connect(m_progressSlider, &QSlider::sliderPressed, this, [this]() {
        m_userSeeking = true;
    });
    connect(m_progressSlider, &QSlider::sliderMoved, this, [this](int value) {
        m_timeLabel->setText(formatTime(value) + QStringLiteral(" / ") + formatTime(m_durationMs));
    });
    connect(m_progressSlider, &QSlider::sliderReleased, this, [this]() {
        m_userSeeking = false;
        emit seekRequested(m_progressSlider->value());
    });

    installEventFilter(this);
    const QList<QWidget *> childWidgets = findChildren<QWidget *>();
    for (QWidget *child : childWidgets) {
        child->installEventFilter(this);
    }
}


void LyricsWindow::setSingleRepeat(bool enabled)
{
    const QSignalBlocker blocker(m_repeatButton);
    m_repeatButton->setChecked(enabled);
    m_repeatButton->setText(enabled ? QStringLiteral("↻1") : QStringLiteral("↻×"));
    m_repeatButton->setToolTip(enabled ? QStringLiteral("单曲循环已开启，点击关闭")
                                      : QStringLiteral("单曲循环已关闭，点击开启"));
}


bool LyricsWindow::isLocked() const
{
    return m_locked;
}


void LyricsWindow::setSongs(const QStringList &titles)
{
    m_songTitles = titles;
    m_songList->clear();

    QVector<int> sortedIndexes;
    sortedIndexes.reserve(titles.size());
    for (int index = 0; index < titles.size(); ++index) {
        sortedIndexes.append(index);
    }
    std::sort(sortedIndexes.begin(), sortedIndexes.end(), [&titles](int left, int right) {
        return QString::localeAwareCompare(titles.at(left), titles.at(right)) < 0;
    });

    for (const int index : sortedIndexes) {
        auto *item = new QListWidgetItem(titles.at(index), m_songList);
        item->setData(Qt::UserRole, index);
    }
    m_songButton->setEnabled(!titles.isEmpty());
}


void LyricsWindow::setPlaylists(const QStringList &titles, int currentIndex)
{
    m_playlistTitles = titles;
    m_playlistList->clear();
    for (int index = 0; index < titles.size(); ++index) {
        auto *item = new QListWidgetItem(titles.at(index), m_playlistList);
        item->setData(Qt::UserRole, index);
        if (index == currentIndex) {
            m_playlistList->setCurrentItem(item);
        }
    }
    m_playlistButton->setEnabled(!titles.isEmpty());
    if (currentIndex >= 0 && currentIndex < titles.size()) {
        m_playlistButton->setToolTip(
            QStringLiteral("选择歌单（当前：%1）").arg(titles.at(currentIndex)));
    } else {
        m_playlistButton->setToolTip(QStringLiteral("选择歌单"));
    }
}


void LyricsWindow::setLyric(const QString &text)
{
    m_lyricLabel->setText(text);
    updateLyricFont();
}


void LyricsWindow::setTrack(const QString &title)
{
    m_trackTitle = title;
    updateTrackLabel();
    setWindowTitle(title.isEmpty()
        ? QStringLiteral("On Screen Music")
        : QStringLiteral("On Screen Music - %1").arg(title));
}


void LyricsWindow::setPlaybackState(bool playing)
{
    m_playButton->setText(playing ? QStringLiteral("⏸") : QStringLiteral("▶"));
    m_playButton->setToolTip(playing ? QStringLiteral("暂停") : QStringLiteral("播放"));
}


void LyricsWindow::setPlaybackPosition(qint64 positionMs, qint64 durationMs)
{
    m_durationMs = qMax<qint64>(0, durationMs);
    if (!m_userSeeking) {
        const int maximum = static_cast<int>(qMin<qint64>(m_durationMs, INT_MAX));
        m_progressSlider->setRange(0, maximum);
        m_progressSlider->setValue(static_cast<int>(qBound<qint64>(0, positionMs, maximum)));
        m_timeLabel->setText(formatTime(positionMs) + QStringLiteral(" / ")
                             + formatTime(m_durationMs));
    }
}


void LyricsWindow::setVolume(int volume)
{
    const QSignalBlocker blocker(m_volumeSlider);
    m_volumeSlider->setValue(qBound(0, volume, 20));
}


void LyricsWindow::setLocked(bool locked)
{
    if (m_locked == locked) {
        return;
    }
    m_locked = locked;
    m_songPopup->hide();
    m_playlistPopup->hide();
    m_volumePopup->hide();
    m_controlPanel->setEnabled(!locked);
    m_controlOpacity->setOpacity(locked ? 0.0 : 1.0);

    const bool wasVisible = isVisible();
    const QPoint currentPosition = pos();
    setWindowFlag(Qt::WindowTransparentForInput, locked);
    if (wasVisible) {
        show();
        move(currentPosition);
    }
    emit lockedChanged(locked);
}


void LyricsWindow::toggleLocked()
{
    setLocked(!m_locked);
}


void LyricsWindow::showSongSelector()
{
    if (m_songTitles.isEmpty()) {
        return;
    }
    if (m_locked) {
        setLocked(false);
    }
    showWindowAndRaise();
    m_songSearch->clear();
    for (int index = 0; index < m_songList->count(); ++index) {
        m_songList->item(index)->setHidden(false);
    }
    showPopupNearWidget(m_songPopup, m_songButton);
    m_songSearch->setFocus();
}


void LyricsWindow::showPlaylistSelector()
{
    if (m_playlistTitles.isEmpty()) {
        return;
    }
    if (m_locked) {
        setLocked(false);
    }
    showWindowAndRaise();
    showPopupNearWidget(m_playlistPopup, m_playlistButton);
    m_playlistList->setFocus();
}


void LyricsWindow::showWindowAndRaise()
{
    show();
    raise();
    if (!m_locked) {
        activateWindow();
    }
}


bool LyricsWindow::eventFilter(QObject *watched, QEvent *event)
{
    Q_UNUSED(watched)
    if (m_locked) {
        return QWidget::eventFilter(watched, event);
    }

    if (event->type() == QEvent::MouseButtonPress) {
        auto *mouseEvent = static_cast<QMouseEvent *>(event);
        if (mouseEvent->button() == Qt::MiddleButton) {
            m_middleDraggingWindow = true;
            m_dragOffset = mouseEvent->globalPos() - frameGeometry().topLeft();
            return true;
        }
    } else if (event->type() == QEvent::MouseMove && m_middleDraggingWindow) {
        auto *mouseEvent = static_cast<QMouseEvent *>(event);
        if (mouseEvent->buttons() & Qt::MiddleButton) {
            move(mouseEvent->globalPos() - m_dragOffset);
            return true;
        }
        m_middleDraggingWindow = false;
    } else if (event->type() == QEvent::MouseButtonRelease && m_middleDraggingWindow) {
        auto *mouseEvent = static_cast<QMouseEvent *>(event);
        if (mouseEvent->button() == Qt::MiddleButton) {
            m_middleDraggingWindow = false;
            AppSettings().setValue(QStringLiteral("Window/Position"), pos());
            return true;
        }
    }
    return QWidget::eventFilter(watched, event);
}


void LyricsWindow::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    if (!m_initialPositionApplied) {
        m_initialPositionApplied = true;
        moveToInitialPosition();
    }
}


void LyricsWindow::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateTrackLabel();
    updateLyricFont();
}


void LyricsWindow::mousePressEvent(QMouseEvent *event)
{
    if (!m_locked && event->button() == Qt::LeftButton) {
        m_draggingWindow = true;
        m_dragOffset = event->globalPos() - frameGeometry().topLeft();
        event->accept();
        return;
    }
    QWidget::mousePressEvent(event);
}


void LyricsWindow::mouseMoveEvent(QMouseEvent *event)
{
    if (m_draggingWindow && (event->buttons() & Qt::LeftButton)) {
        move(event->globalPos() - m_dragOffset);
        event->accept();
        return;
    }
    QWidget::mouseMoveEvent(event);
}


void LyricsWindow::mouseReleaseEvent(QMouseEvent *event)
{
    if (m_draggingWindow && event->button() == Qt::LeftButton) {
        m_draggingWindow = false;
        AppSettings().setValue(QStringLiteral("Window/Position"), pos());
        event->accept();
        return;
    }
    QWidget::mouseReleaseEvent(event);
}


void LyricsWindow::createSongPopup()
{
    m_songPopup = new QFrame(this, Qt::Popup | Qt::FramelessWindowHint);
    m_songPopup->setObjectName(QStringLiteral("popupPanel"));
    m_songPopup->resize(430, 360);
    m_songPopup->setStyleSheet(QStringLiteral(R"(
        QFrame#popupPanel { background: #202124; border: 1px solid #555; border-radius: 8px; }
        QLineEdit { color: white; background: #303134; border: 1px solid #666; border-radius: 6px; padding: 7px; }
        QListWidget { color: white; background: transparent; border: none; outline: none; }
        QListWidget::item { padding: 7px; border-radius: 5px; }
        QListWidget::item:hover, QListWidget::item:selected { background: #4b4d51; }
    )"));
    m_songSearch = new QLineEdit(m_songPopup);
    m_songSearch->setPlaceholderText(QStringLiteral("搜索歌曲"));
    m_songList = new QListWidget(m_songPopup);

    auto *layout = new QVBoxLayout(m_songPopup);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(8);
    layout->addWidget(m_songSearch);
    layout->addWidget(m_songList, 1);

    connect(m_songSearch, &QLineEdit::textChanged, this, [this](const QString &text) {
        for (int index = 0; index < m_songList->count(); ++index) {
            QListWidgetItem *item = m_songList->item(index);
            item->setHidden(!item->text().contains(text, Qt::CaseInsensitive));
        }
    });
    connect(m_songList, &QListWidget::itemClicked, this, &LyricsWindow::chooseSong);
    connect(m_songList, &QListWidget::itemActivated, this, &LyricsWindow::chooseSong);
}


void LyricsWindow::createVolumePopup()
{
    m_volumePopup = new QFrame(this, Qt::Popup | Qt::FramelessWindowHint);
    m_volumePopup->setObjectName(QStringLiteral("volumePopup"));
    m_volumePopup->resize(220, 54);
    m_volumePopup->setStyleSheet(QStringLiteral(
        "QFrame#volumePopup { background: #202124; border: 1px solid #555; border-radius: 8px; }"));
    m_volumeSlider = new QSlider(Qt::Horizontal, m_volumePopup);
    m_volumeSlider->setRange(0, 20);

    auto *layout = new QHBoxLayout(m_volumePopup);
    layout->setContentsMargins(14, 8, 14, 8);
    layout->addWidget(m_volumeSlider);
    connect(m_volumeSlider, &QSlider::valueChanged, this, &LyricsWindow::volumeRequested);
}


void LyricsWindow::createPlaylistPopup()
{
    m_playlistPopup = new QFrame(this, Qt::Popup | Qt::FramelessWindowHint);
    m_playlistPopup->setObjectName(QStringLiteral("playlistPopup"));
    m_playlistPopup->resize(360, 300);
    m_playlistPopup->setStyleSheet(QStringLiteral(R"(
        QFrame#playlistPopup { background: #202124; border: 1px solid #555; border-radius: 8px; }
        QListWidget { color: white; background: transparent; border: none; outline: none; }
        QListWidget::item { padding: 8px; border-radius: 5px; }
        QListWidget::item:hover, QListWidget::item:selected { background: #4b4d51; }
    )"));
    m_playlistList = new QListWidget(m_playlistPopup);

    auto *layout = new QVBoxLayout(m_playlistPopup);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->addWidget(m_playlistList);

    connect(m_playlistList, &QListWidget::itemClicked,
            this, &LyricsWindow::choosePlaylist);
    connect(m_playlistList, &QListWidget::itemActivated,
            this, &LyricsWindow::choosePlaylist);
}


void LyricsWindow::moveToInitialPosition()
{
    const AppSettings settings;
    if (settings.contains(QStringLiteral("Window/Position"))) {
        const QPoint savedPosition =
            settings.value(QStringLiteral("Window/Position")).toPoint();
        const QRect savedGeometry(savedPosition, size());
        for (QScreen *screen : QGuiApplication::screens()) {
            if (screen->availableGeometry().intersects(savedGeometry)) {
                move(savedPosition);
                return;
            }
        }
    }

    QScreen *screen = QGuiApplication::primaryScreen();
    if (!screen) {
        return;
    }
    const QRect available = screen->availableGeometry();
    move(available.x() + (available.width() - width()) / 2,
         available.y() + available.height() - height() - 60);
}


void LyricsWindow::showPopupNearWidget(QWidget *popup, QWidget *anchor)
{
    const QPoint anchorBottom = anchor->mapToGlobal(QPoint(0, anchor->height() + 6));
    QScreen *screen = QGuiApplication::screenAt(anchorBottom);
    if (!screen) {
        screen = QGuiApplication::primaryScreen();
    }
    QPoint popupPosition(anchorBottom.x() + (anchor->width() - popup->width()) / 2,
                         anchorBottom.y());
    if (screen) {
        const QRect available = screen->availableGeometry();
        popupPosition.setX(qBound(available.left(), popupPosition.x(),
                                  available.right() - popup->width() + 1));
        if (popupPosition.y() + popup->height() > available.bottom()) {
            popupPosition.setY(anchor->mapToGlobal(QPoint(0, -popup->height() - 6)).y());
        }
    }
    popup->move(popupPosition);
    popup->show();
    popup->raise();
    popup->activateWindow();
}


void LyricsWindow::chooseSong(QListWidgetItem *item)
{
    if (!item || !m_songPopup->isVisible()) {
        return;
    }
    const int index = item->data(Qt::UserRole).toInt();
    m_songPopup->hide();
    emit songRequested(index);
}


void LyricsWindow::choosePlaylist(QListWidgetItem *item)
{
    if (!item || !m_playlistPopup->isVisible()) {
        return;
    }
    const int index = item->data(Qt::UserRole).toInt();
    m_playlistPopup->hide();
    emit playlistRequested(index);
}


void LyricsWindow::updateTrackLabel()
{
    if (!m_trackLabel) {
        return;
    }
    m_trackLabel->setText(
        m_trackLabel->fontMetrics().elidedText(
            m_trackTitle, Qt::ElideRight, m_trackLabel->contentsRect().width()));
    m_trackLabel->setToolTip(m_trackTitle);
}


void LyricsWindow::updateLyricFont()
{
    if (!m_lyricLabel) {
        return;
    }
    const QString text = m_lyricLabel->text();
    const int availableWidth = m_lyricLabel->contentsRect().width();
    if (text.isEmpty() || availableWidth <= 0) {
        return;
    }

    QFont font = m_lyricLabel->font();
    int smallest = 1;
    int largest = 60;
    int bestSize = 1;
    while (smallest <= largest) {
        const int candidateSize = smallest + (largest - smallest) / 2;
        font.setPixelSize(candidateSize);
        if (QFontMetrics(font).horizontalAdvance(text) <= availableWidth) {
            bestSize = candidateSize;
            smallest = candidateSize + 1;
        } else {
            largest = candidateSize - 1;
        }
    }

    if (m_lyricLabel->font().pixelSize() != bestSize) {
        font.setPixelSize(bestSize);
        m_lyricLabel->setFont(font);
    }
}


QString LyricsWindow::formatTime(qint64 milliseconds)
{
    const qint64 totalSeconds = qMax<qint64>(0, milliseconds) / 1000;
    return QStringLiteral("%1:%2")
        .arg(totalSeconds / 60, 2, 10, QLatin1Char('0'))
        .arg(totalSeconds % 60, 2, 10, QLatin1Char('0'));
}

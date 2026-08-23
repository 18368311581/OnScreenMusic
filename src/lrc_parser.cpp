#include "lrc_parser.h"

#include <QFile>
#include <QRegularExpression>

#include <algorithm>


QVector<LrcLine> LrcParser::parseFile(const QString &filePath, bool *instrumental)
{
    if (instrumental) {
        *instrumental = false;
    }
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly)) {
        return {};
    }

    const QString content = QString::fromUtf8(file.readAll());
    const int lineBreak = content.indexOf(QRegularExpression(QStringLiteral("[\r\n]")));
    QString firstLine = lineBreak >= 0 ? content.left(lineBreak) : content;
    if (!firstLine.isEmpty() && firstLine.front() == QChar::ByteOrderMark) {
        firstLine.remove(0, 1);
    }
    if (firstLine.trimmed().compare(
            QStringLiteral("#INSTRUMENTAL"), Qt::CaseInsensitive) == 0) {
        if (instrumental) {
            *instrumental = true;
        }
        return {};
    }

    const QRegularExpression timestampPattern(
        QStringLiteral(R"(\[(\d+):(\d{2})(?:\.(\d{1,3}))?\])"));

    QVector<LrcLine> result;
    const QStringList sourceLines = content.split(QRegularExpression(QStringLiteral("[\r\n]+")),
                                                  Qt::SkipEmptyParts);
    for (const QString &sourceLine : sourceLines) {
        QVector<qint64> timestamps;
        QRegularExpressionMatchIterator matches = timestampPattern.globalMatch(sourceLine);
        while (matches.hasNext()) {
            const QRegularExpressionMatch match = matches.next();
            const int minutes = match.captured(1).toInt();
            const int seconds = match.captured(2).toInt();
            if (seconds >= 60) {
                continue;
            }

            const QString fraction = match.captured(3);
            int milliseconds = 0;
            if (fraction.size() == 1) {
                milliseconds = fraction.toInt() * 100;
            } else if (fraction.size() == 2) {
                milliseconds = fraction.toInt() * 10;
            } else if (fraction.size() == 3) {
                milliseconds = fraction.toInt();
            }
            timestamps.append((static_cast<qint64>(minutes) * 60 + seconds) * 1000
                              + milliseconds);
        }

        if (timestamps.isEmpty()) {
            continue;
        }

        QString lyricText = sourceLine;
        lyricText.remove(timestampPattern);
        lyricText = lyricText.trimmed();
        for (const qint64 timestamp : timestamps) {
            result.append({timestamp, lyricText});
        }
    }

    std::stable_sort(result.begin(), result.end(), [](const LrcLine &left, const LrcLine &right) {
        return left.timeMs < right.timeMs;
    });
    return result;
}


bool LrcParser::textAt(
    const QVector<LrcLine> &lines, qint64 positionMs, QString *text,
    qint64 maximumDisplayDurationMs)
{
    if (lines.isEmpty()) {
        return false;
    }

    const auto next = std::upper_bound(
        lines.cbegin(), lines.cend(), positionMs,
        [](qint64 value, const LrcLine &line) { return value < line.timeMs; });
    if (next == lines.cbegin()) {
        return false;
    }

    const auto current = std::prev(next);
    if (maximumDisplayDurationMs >= 0
        && positionMs - current->timeMs >= maximumDisplayDurationMs) {
        return false;
    }

    if (text) {
        *text = current->text;
    }
    return true;
}

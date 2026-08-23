#pragma once

#include <QString>
#include <QVector>


struct LrcLine {
    qint64 timeMs = 0;
    QString text;
};


class LrcParser {
public:
    static QVector<LrcLine> parseFile(const QString &filePath, bool *instrumental = nullptr);
    static bool textAt(const QVector<LrcLine> &lines, qint64 positionMs, QString *text,
                       qint64 maximumDisplayDurationMs = -1);
};

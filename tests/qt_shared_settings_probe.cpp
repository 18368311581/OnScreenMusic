// Temporary-directory interoperability probe; it never reads the real library.
#include "app_settings.h"
#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPoint>
#include <QThread>
#include <iostream>

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    const QString mode = app.arguments().value(1);
    if (mode == QStringLiteral("seed")) {
        AppSettings settings;
        settings.setValue(QStringLiteral("Window/Position"), QPoint(401, 512));
        settings.setValue(QStringLiteral("Library/PlaylistFile"), QStringLiteral("中文,歌单.txt"));
        settings.setValue(QStringLiteral("Playback/SingleRepeat"), true);
        settings.setValue(QStringLiteral("Audio/Volume"), 9);
        settings.setValue(QStringLiteral("Unknown/List"), QStringList{QStringLiteral("a,b"), QStringLiteral("中文")});
    } else if (mode == QStringLiteral("loop")) {
        for (int index = 0; index < 75; ++index) {
            {
                AppSettings settings;
                settings.setValue(QStringLiteral("Playback/PositionMs"), index * 101);
            }
            QThread::msleep(8);
        }
    }
    const AppSettings settings;
    QJsonObject output;
    output.insert(QStringLiteral("root"), settings.value(QStringLiteral("Library/Root")).toString());
    output.insert(QStringLiteral("work"), settings.value(QStringLiteral("Workshop/Work")).toString());
    output.insert(QStringLiteral("api"), settings.value(QStringLiteral("Workshop/ApiKey")).toString());
    output.insert(QStringLiteral("playlist"), settings.value(QStringLiteral("Library/PlaylistFile")).toString());
    output.insert(QStringLiteral("volume"), settings.value(QStringLiteral("Audio/Volume")).toInt());
    output.insert(QStringLiteral("position"), static_cast<int>(settings.value(QStringLiteral("Playback/PositionMs")).toLongLong()));
    output.insert(QStringLiteral("repeat"), settings.value(QStringLiteral("Playback/SingleRepeat")).toBool());
    output.insert(QStringLiteral("point_ok"), settings.value(QStringLiteral("Window/Position")).toPoint() == QPoint(401, 512));
    output.insert(QStringLiteral("list_ok"), settings.value(QStringLiteral("Unknown/List")).toStringList()
        == QStringList{QStringLiteral("a,b"), QStringLiteral("中文")});
    std::cout << QJsonDocument(output).toJson(QJsonDocument::Compact).constData() << std::endl;
    return settings.status() == QSettings::NoError ? 0 : 2;
}

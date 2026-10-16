#pragma once

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QSettings>

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

// The same named guard is used by Python when it updates this INI.
// Base order holds the guard through QSettings' destructor and final flush.
class AppSettingsGuard {
public:
    explicit AppSettingsGuard(const QString &path)
    {
        const QByteArray token = QCryptographicHash::hash(
            QDir::fromNativeSeparators(QDir::cleanPath(path)).toCaseFolded().toUtf8(),
            QCryptographicHash::Sha256).toHex().left(20);
        const QString name = QStringLiteral("Local\\OnScreenMusic.Settings.")
            + QString::fromLatin1(token);
        m_mutex = CreateMutexW(nullptr, FALSE,
                              reinterpret_cast<LPCWSTR>(name.utf16()));
        if (m_mutex) {
            const DWORD result = WaitForSingleObject(m_mutex, INFINITE);
            m_acquired = result == WAIT_OBJECT_0 || result == WAIT_ABANDONED;
        }
    }

    ~AppSettingsGuard()
    {
        if (m_acquired) {
            ReleaseMutex(m_mutex);
        }
        if (m_mutex) {
            CloseHandle(m_mutex);
        }
    }

private:
    HANDLE m_mutex = nullptr;
    bool m_acquired = false;
};

class AppSettings final : private AppSettingsGuard, public QSettings {
public:
    explicit AppSettings(QObject *parent = nullptr)
        : AppSettingsGuard(filePath()),
          QSettings(filePath(), QSettings::IniFormat, parent)
    {
        setIniCodec("UTF-8");
        sync();
    }

    ~AppSettings() override
    {
        sync();
    }

    static QString filePath()
    {
        return QDir(QCoreApplication::applicationDirPath())
            .filePath(QStringLiteral("OnScreenMusic.ini"));
    }
};

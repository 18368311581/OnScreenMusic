QT += core gui widgets multimedia

CONFIG += c++17
CONFIG -= app_bundle

TEMPLATE = app
TARGET = OnScreenMusic

DEFINES += QT_DEPRECATED_WARNINGS

SOURCES += \
    src/main.cpp \
    src/global_hotkey_manager.cpp \
    src/lrc_parser.cpp \
    src/lyrics_window.cpp \
    src/player_controller.cpp

HEADERS += \
    src/app_settings.h \
    src/global_hotkey_manager.h \
    src/lrc_parser.h \
    src/lyrics_window.h \
    src/player_controller.h

RESOURCES += resources.qrc

win32-g++ {
    RC_ICONS = assets/app_icon.ico
    QMAKE_CXXFLAGS += -finput-charset=UTF-8 -fexec-charset=UTF-8
    LIBS += -luser32
}

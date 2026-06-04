cmake_minimum_required(VERSION 3.20)

project(GridSimulatorExe LANGUAGES NONE)

if(NOT DEFINED Python3_EXECUTABLE)
    find_program(GRID_SIMULATOR_PATH_PYTHON NAMES python python3)
    if(GRID_SIMULATOR_PATH_PYTHON)
        set(Python3_EXECUTABLE "${GRID_SIMULATOR_PATH_PYTHON}" CACHE FILEPATH "Python interpreter untuk build Grid Simulator" FORCE)
    endif()
endif()

find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(GRID_SIMULATOR_NAME "GridSimulator" CACHE STRING "Nama file executable yang dibuat.")
set(GRID_SIMULATOR_ENTRY "${CMAKE_CURRENT_SOURCE_DIR}/demo.py" CACHE FILEPATH "Entry point aplikasi.")
option(GRID_SIMULATOR_ONEFILE "Buat satu file .exe dengan PyInstaller." ON)
option(GRID_SIMULATOR_WINDOWED "Jalankan .exe tanpa console window di Windows." ON)

set(GRID_SIMULATOR_VENV "${CMAKE_BINARY_DIR}/.venv")
set(GRID_SIMULATOR_DIST "${CMAKE_BINARY_DIR}/dist")
set(GRID_SIMULATOR_WORK "${CMAKE_BINARY_DIR}/pyinstaller-work")
set(GRID_SIMULATOR_SPEC "${CMAKE_BINARY_DIR}/pyinstaller-spec")
set(GRID_SIMULATOR_STAMP "${CMAKE_BINARY_DIR}/pyinstaller-deps.stamp")

if(WIN32)
    set(GRID_SIMULATOR_VENV_PYTHON "${GRID_SIMULATOR_VENV}/Scripts/python.exe")
    set(GRID_SIMULATOR_EXE_SUFFIX ".exe")
else()
    set(GRID_SIMULATOR_VENV_PYTHON "${GRID_SIMULATOR_VENV}/bin/python")
    set(GRID_SIMULATOR_EXE_SUFFIX "")
endif()

if(GRID_SIMULATOR_ONEFILE)
    set(GRID_SIMULATOR_MODE_ARGS --onefile)
    set(GRID_SIMULATOR_OUTPUT "${GRID_SIMULATOR_DIST}/${GRID_SIMULATOR_NAME}${GRID_SIMULATOR_EXE_SUFFIX}")
else()
    set(GRID_SIMULATOR_MODE_ARGS --onedir)
    set(GRID_SIMULATOR_OUTPUT "${GRID_SIMULATOR_DIST}/${GRID_SIMULATOR_NAME}/${GRID_SIMULATOR_NAME}${GRID_SIMULATOR_EXE_SUFFIX}")
endif()

if(WIN32 AND GRID_SIMULATOR_WINDOWED)
    set(GRID_SIMULATOR_WINDOW_ARGS --windowed)
else()
    set(GRID_SIMULATOR_WINDOW_ARGS)
endif()

if(WIN32)
    set(GRID_SIMULATOR_REPORT_TEMPLATE "${CMAKE_CURRENT_SOURCE_DIR}/docs/report-template.html$<SEMICOLON>docs")
else()
    set(GRID_SIMULATOR_REPORT_TEMPLATE "${CMAKE_CURRENT_SOURCE_DIR}/docs/report-template.html:docs")
endif()

add_custom_command(
    OUTPUT "${GRID_SIMULATOR_STAMP}"
    COMMAND "${Python3_EXECUTABLE}" -m venv "${GRID_SIMULATOR_VENV}"
    COMMAND "${GRID_SIMULATOR_VENV_PYTHON}" -m pip install --upgrade pip
    COMMAND "${GRID_SIMULATOR_VENV_PYTHON}" -m pip install -r "${CMAKE_CURRENT_SOURCE_DIR}/requirements.txt" pyinstaller
    COMMAND "${CMAKE_COMMAND}" -E touch "${GRID_SIMULATOR_STAMP}"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/requirements.txt"
    COMMENT "Menyiapkan virtual environment dan dependency Python"
    VERBATIM
)

add_custom_command(
    OUTPUT "${GRID_SIMULATOR_OUTPUT}"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${GRID_SIMULATOR_DIST}"
    COMMAND "${GRID_SIMULATOR_VENV_PYTHON}" -m PyInstaller
            --noconfirm
            --clean
            --name "${GRID_SIMULATOR_NAME}"
            --distpath "${GRID_SIMULATOR_DIST}"
            --workpath "${GRID_SIMULATOR_WORK}"
            --specpath "${GRID_SIMULATOR_SPEC}"
            --collect-all dearpygui
            --collect-all pandapower
            --add-data "${GRID_SIMULATOR_REPORT_TEMPLATE}"
            ${GRID_SIMULATOR_MODE_ARGS}
            ${GRID_SIMULATOR_WINDOW_ARGS}
            "${GRID_SIMULATOR_ENTRY}"
    DEPENDS
            "${GRID_SIMULATOR_STAMP}"
            "${GRID_SIMULATOR_ENTRY}"
            "${CMAKE_CURRENT_SOURCE_DIR}/canvas_logic.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/engine.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/qt_app.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/qt_canvas.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/qt_model.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/report_export.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/state.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/docs/report-template.html"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMENT "Membuat executable Grid Simulator"
    VERBATIM
)

add_custom_target(grid-simulator-exe ALL
    DEPENDS "${GRID_SIMULATOR_OUTPUT}"
)

add_custom_target(run-grid-simulator-exe
    COMMAND "${GRID_SIMULATOR_OUTPUT}"
    DEPENDS grid-simulator-exe
    WORKING_DIRECTORY "${GRID_SIMULATOR_DIST}"
    COMMENT "Menjalankan executable Grid Simulator"
    VERBATIM
)

message(STATUS "Output executable: ${GRID_SIMULATOR_OUTPUT}")

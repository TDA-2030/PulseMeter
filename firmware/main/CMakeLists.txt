
file(GLOB_RECURSE SOURCES "${CMAKE_CURRENT_LIST_DIR}/*.c")
file(GLOB_RECURSE CPP_SOURCES "${CMAKE_CURRENT_LIST_DIR}/*.cpp")

idf_component_register(SRCS 
    ${SOURCES} ${CPP_SOURCES}

    INCLUDE_DIRS 
    . 
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-format -Wno-empty-body -Wno-error=jump-misses-init)

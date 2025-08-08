
file(GLOB_RECURSE SOURCES "${CMAKE_CURRENT_LIST_DIR}/*.c")
file(GLOB_RECURSE CPP_SOURCES "${CMAKE_CURRENT_LIST_DIR}/*.cpp")

idf_component_register(SRCS 
    ${SOURCES} ${CPP_SOURCES}

    INCLUDE_DIRS 
    . 
    wifi
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-format -Wno-empty-body -Wno-error=jump-misses-init)


if(CONFIG_EXAMPLE_WEB_DEPLOY_SF)
    set(WEB_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../front/web-demo")
    if(EXISTS ${WEB_SRC_DIR}/dist)
        spiffs_create_partition_image(www ${WEB_SRC_DIR}/dist FLASH_IN_PROJECT)
    else()
        message(FATAL_ERROR "${WEB_SRC_DIR}/dist doesn't exit. Please run 'npm run build' in ${WEB_SRC_DIR}")
    endif()
endif()

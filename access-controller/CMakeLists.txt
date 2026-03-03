set(app_sources
    app.c
    rc522.c
)

# 절대 경로를 명시하여 컴파일러가 도망가지 못하게 막습니다.
set(app_includes
    /root/microros/firmware/freertos_apps/apps/FactoryDoor_service
)

set(app_libraries
    m
)

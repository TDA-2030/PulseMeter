/*

  */
#ifndef __BOARD_H_
#define __BOARD_H_

#include "i2c_bus.h"


#ifdef __cplusplus
extern "C" {
#endif

#define BOARD_IO_METER1 5
#define BOARD_IO_METER2 6


#define BOARD_IO_IMU_SDA 2
#define BOARD_IO_IMU_SCL 3

#define BOARD_IO_LED_RED 10
#define BOARD_IO_LED_GREEN 1


esp_err_t bsp_i2c_init(void);
i2c_bus_handle_t bsp_i2c_get_handle(void);


#ifdef __cplusplus
}
#endif

#endif

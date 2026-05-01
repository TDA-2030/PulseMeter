#ifndef __BOARD_H_
#define __BOARD_H_

#include "esp_err.h"


#ifdef __cplusplus
extern "C" {
#endif

#define BOARD_IO_METER1 5
#define BOARD_IO_METER2 6
#define BOARD_IO_LED_STRIP1 4
#define BOARD_IO_LED_STRIP2 7

esp_err_t board_init(void);

#ifdef __cplusplus
}
#endif

#endif

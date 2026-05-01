#ifndef __LED_H_
#define __LED_H_

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t led_init(int gpio, uint32_t max_leds);
esp_err_t led_deinit(void);
esp_err_t led_set_pixel(uint32_t index, uint32_t red, uint32_t green, uint32_t blue);
esp_err_t led_set_pixel_hsv(uint32_t index, uint32_t hue, uint32_t saturation, uint32_t value);
esp_err_t led_refresh(void);
esp_err_t led_clear(void);

#ifdef __cplusplus
}
#endif

#endif

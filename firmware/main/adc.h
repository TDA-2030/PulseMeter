#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize ADC in continuous mode
 */
void adc_init(void);

/**
 * @brief Read voltage from ADC
 * @return Voltage in mV, or -1.0 if error
 */
float adc_read_voltage(void);

#ifdef __cplusplus
}
#endif

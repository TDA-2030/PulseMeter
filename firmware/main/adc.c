/*
 * SPDX-FileCopyrightText: 2022-2023 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "soc/soc_caps.h"
#include "esp_log.h"

#include "driver/gpio.h"

#include "soc/soc_caps.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"

#include "adc.h"

#define POWER_ADC_CHANNEL ADC_CHANNEL_0
#define VOLT_FILTER_ALPHA   0.9f
static const char *TAG = "adc";

static adc_oneshot_unit_handle_t power_adc_handle = NULL;
static adc_cali_handle_t power_adc_cali_handle = NULL;

static int adc_raw = 0;
static esp_err_t adc_calibration_init(adc_unit_t unit, adc_channel_t channel, adc_atten_t atten, adc_cali_handle_t *out_handle);
static void adc_calibration_deinit(adc_cali_handle_t handle);
static int filtered_voltage = 0;

void adc_init(void)
{
    //-------------ADC Init---------------//

    adc_oneshot_unit_init_cfg_t init_config1 = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config1, &power_adc_handle));

    //-------------ADC Config---------------//
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = SOC_ADC_RTC_MAX_BITWIDTH,
        .atten = ADC_ATTEN_DB_12,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(power_adc_handle, POWER_ADC_CHANNEL, &config));

    //-------------ADC Calibration Init---------------//

    ESP_ERROR_CHECK(adc_calibration_init(ADC_UNIT_1, POWER_ADC_CHANNEL, ADC_ATTEN_DB_12, &power_adc_cali_handle));

}

float adc_read_voltage(void)
{
    ESP_ERROR_CHECK(adc_oneshot_read(power_adc_handle, POWER_ADC_CHANNEL, &adc_raw));
    int voltage = 0;
    ESP_ERROR_CHECK(adc_cali_raw_to_voltage(power_adc_cali_handle, adc_raw, &voltage));
    if (filtered_voltage == 0) {
        filtered_voltage = voltage;
    }
    filtered_voltage = VOLT_FILTER_ALPHA * voltage + (1.0f - VOLT_FILTER_ALPHA) * filtered_voltage;
    return filtered_voltage* 4.17f * 11.0f / 4096 ;
}


static esp_err_t adc_calibration_init(adc_unit_t unit, adc_channel_t channel, adc_atten_t atten, adc_cali_handle_t *out_handle)
{
    adc_cali_handle_t handle = NULL;
    esp_err_t ret = ESP_FAIL;
    bool calibrated = false;

#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    if (!calibrated) {
        ESP_LOGI(TAG, "calibration scheme version is %s", "Curve Fitting");
        adc_cali_curve_fitting_config_t cali_config = {
            .unit_id = unit,
            .atten = atten,
            .bitwidth = SOC_ADC_RTC_MAX_BITWIDTH,
        };
        ret = adc_cali_create_scheme_curve_fitting(&cali_config, &handle);
        if (ret == ESP_OK) {
            calibrated = true;
        }
    }
#endif

#if ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
    if (!calibrated) {
        ESP_LOGI(TAG, "calibration scheme version is %s", "Line Fitting");
        adc_cali_line_fitting_config_t cali_config = {
            .unit_id = unit,
            .atten = atten,
            .bitwidth = SOC_ADC_RTC_MAX_BITWIDTH,
        };
        ret = adc_cali_create_scheme_line_fitting(&cali_config, &handle);
        if (ret == ESP_OK) {
            calibrated = true;
        }
    }
#endif

    *out_handle = handle;
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "Calibration Success");
    } else if (ret == ESP_ERR_NOT_SUPPORTED || !calibrated) {
        ESP_LOGW(TAG, "eFuse not burnt, skip software calibration");
    } else {
        ESP_LOGE(TAG, "Invalid arg or no memory");
    }

    return calibrated ? ESP_OK : ESP_FAIL;
}

__attribute__((unused)) static void adc_calibration_deinit(adc_cali_handle_t handle)
{
    ESP_LOGI(TAG, "deregister %s calibration scheme", "Curve Fitting");
    ESP_ERROR_CHECK(adc_cali_delete_scheme_curve_fitting(handle));
}

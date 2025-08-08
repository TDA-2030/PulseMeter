/*

  */
#ifndef _HELPER_H_
#define _HELPER_H_

#ifdef __cplusplus
extern "C" {
#endif

#define __HERE() printf("%s:%d - %s\n", __FILE__, __LINE__, __func__)

#define RESTART_COUNT_RESET 6

esp_err_t iot_param_save(const char* space_name, const char* key, void *param, uint16_t len);

esp_err_t iot_param_load(const char* space_name, const char* key, void* dest);

esp_err_t iot_param_erase(const char* space_name, const char* key);

int restart_count_get();

void set_time(int year, int month, int day, int hour, int min, int sec, bool is_utc);

#ifdef __cplusplus
}
#endif

#endif

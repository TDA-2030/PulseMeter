#include <string.h>
#include "esp_log.h"
#include "setting.h"
#include "helper.h"

static const char *TAG = "setting";

Setting g_settings;

Setting::Setting()
{

}

void Setting::restortDefault()
{
    ESP_LOGI(TAG, "restortDefault");
    mode = 0;
 
}

void Setting::print()
{
    ESP_LOGI(TAG, "Settings:");
    ESP_LOGI(TAG, "mode: %d", mode);

    ESP_LOGI(TAG, "checksum: %u", checksum);
}

esp_err_t Setting::load()
{
    esp_err_t ret = iot_param_load(SETTINGS_NAMESPACE, SETTINGS_KEY, this);
    if (ret != ESP_OK || !validateChecksum() || !validateRanges()) {
        ESP_LOGW(TAG, "Failed to load settings or validation failed, error: %s", esp_err_to_name(ret));
        // Initialize with default values
        restortDefault();
        updateChecksum();
        save();
    }
    print();

    return ret;
}

esp_err_t Setting::save()
{
    if (!validateRanges()) {
        ESP_LOGE(TAG, "Settings validation failed, refusing to save");
        return ESP_ERR_INVALID_STATE;
    }
    updateChecksum();
    return iot_param_save(SETTINGS_NAMESPACE, SETTINGS_KEY, this, sizeof(Setting));
}

bool Setting::validateChecksum()
{
    uint32_t calculated = calculateChecksum();
    return 1;//calculated == checksum;
}

void Setting::updateChecksum()
{
    checksum = calculateChecksum();
}

uint32_t Setting::calculateChecksum()
{
    uint32_t sum = 0;
    const uint8_t *data = reinterpret_cast<const uint8_t *>(this);
    // Skip the checksum field itself in the calculation
    for (size_t i = sizeof(checksum); i < sizeof(Setting); i++) {
        sum = (sum << 1) + data[i];
    }
    return sum;
}

bool Setting::validateRanges()
{
    

    return true;
}

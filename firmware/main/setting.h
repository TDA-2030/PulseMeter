/*

  */
#ifndef __SETTING__H_
#define __SETTING__H_

#include <stdint.h>
#include <string>
#include <limits.h>
#include <unordered_map>
#include "esp_err.h"

#define SETTINGS_NAMESPACE "settings"
#define SETTINGS_KEY "main"


template <typename T>
class Parameter
{
protected:
    std::string name; // 参数名称
    T &value; // 参数值
    const T &defaultValue; // 默认值
    size_t length; // 参数长度

public:
    Parameter(std::string _name, T &_value, const T &_defaultValue, size_t _length): 
    name(_name), value(_value), defaultValue(_defaultValue), length(_length) {}

private:
    Parameter(const Parameter &other) = delete;
    // Parameter &operator=(const Parameter &other) = delete;
    Parameter(Parameter &&other) = delete;
};

class Setting {
public:
    Setting();
    esp_err_t load();
    esp_err_t save();

    uint8_t mode;

private:
    // std::unordered_map<std::string, Parameter> parameters; // 存储所有参数
    uint32_t checksum;  // Must be the first member for checksum calculation
    void restortDefault();
    void print();
    bool validateChecksum();
    void updateChecksum();
    uint32_t calculateChecksum();
    bool validateRanges();
};

extern Setting g_settings;

#endif

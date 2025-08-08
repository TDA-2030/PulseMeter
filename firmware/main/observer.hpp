#pragma once
#include <memory>
#include <vector>
#include <stdio.h>

template <typename T>
// 观察者接口
class Observer {
public:
    virtual ~Observer() = default;
    virtual void update(const T &data) = 0;  // 更新 IMU 数据
};


template <typename T>
// 主题接口
class Subject {
public:
    virtual ~Subject() = default;
    virtual void registerObserver(std::shared_ptr<Observer<T>> observer)
    {
        observers.push_back(observer);
    }

    virtual void removeObserver(std::shared_ptr<Observer<T>> observer)
    {
        auto it = std::find(observers.begin(), observers.end(), observer);
        if (it != observers.end()) {
            observers.erase(it);
        } else {
            printf("Observer not found\n");
        }
    }
    virtual void notifyObservers(const T &data)  // 通知所有观察者
    {
        for (const auto &observer : observers) {
            observer->update(data);
        }
    }

protected:
    std::vector<std::shared_ptr<Observer<T>>> observers;  // 观察者列表
};

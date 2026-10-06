#include <algorithm>
#include <chrono>
#include <functional>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

class Talker : public rclcpp::Node
{
  public:
    Talker() : Node("talker")
    {
        // 发布内容与周期可在启动时覆盖：ros2 run cpp_hello talker --ros-args -p message:=hi -p
        // period_ms:=500
        this->declare_parameter<std::string>("message", "hello");
        this->declare_parameter<int>("period_ms", 1000);
        message_ = this->get_parameter("message").as_string();
        const int period_ms =
            std::max(static_cast<int>(this->get_parameter("period_ms").as_int()), 1);

        // 消息类型 String，话题名 hello，队列长度 10
        publisher_ = this->create_publisher<std_msgs::msg::String>("hello", 10);
        timer_ = this->create_wall_timer(std::chrono::milliseconds(period_ms),
                                         std::bind(&Talker::timer_callback, this));
    }

  private:
    void timer_callback()
    {
        auto msg = std_msgs::msg::String();
        msg.data = message_;
        publisher_->publish(msg);
        ++count_;
        RCLCPP_INFO(this->get_logger(), "发布第 %zu 条: %s", count_, msg.data.c_str());
    }

    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
    rclcpp::TimerBase::SharedPtr timer_;
    std::string message_;
    size_t count_ = 0;
};

int main(int argc, char* argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<Talker>());
    rclcpp::shutdown();
    return 0;
}

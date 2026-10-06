#include <functional>
#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

class Listener : public rclcpp::Node
{
  public:
    Listener() : Node("listener")
    {
        // 订阅 hello 话题，收到消息就调用 callback
        subscription_ = this->create_subscription<std_msgs::msg::String>(
            "hello", 10, std::bind(&Listener::callback, this, std::placeholders::_1));
    }

  private:
    void callback(const std_msgs::msg::String::SharedPtr msg) const
    {
        RCLCPP_INFO(this->get_logger(), "收到: %s", msg->data.c_str());
    }

    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
};

int main(int argc, char* argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<Listener>());
    rclcpp::shutdown();
    return 0;
}

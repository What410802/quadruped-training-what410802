#include <chrono>
#include <functional>
#include <memory>

#include "rclcpp/rclcpp.hpp"

using namespace std::chrono_literals;

class HelloNode : public rclcpp::Node
{
  public:
    HelloNode() : Node("hello_node")
    {
        // 每 1 秒调用一次 timer_callback
        timer_ = this->create_wall_timer(1s, std::bind(&HelloNode::timer_callback, this));
    }

  private:
    void timer_callback() { RCLCPP_INFO(this->get_logger(), "hello ros2"); }

    rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char* argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<HelloNode>());
    rclcpp::shutdown();
    return 0;
}

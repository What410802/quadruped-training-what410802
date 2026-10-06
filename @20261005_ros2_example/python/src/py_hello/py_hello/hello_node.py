import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class HelloNode(Node):
    def __init__(self):
        super().__init__('hello_node')  # 节点名，ros2 node list 里会显示这个名字
        # 每 1 秒调用一次 timer_callback
        self.timer = self.create_timer(1.0, self.timer_callback)

    def timer_callback(self):
        self.get_logger().info('hello ros2')


def main(args=None):
    rclpy.init(args=args)
    node = HelloNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()


#include "state_machine.hpp"
#ifdef BUILD_SIMULATION
    #define BACKWARD_HAS_DW 1
    #include "backward.hpp"
    namespace backward{
        backward::SignalHandling sh;
    }
#endif
using namespace types;

MotionStateFeedback StateBase::msfb_ = MotionStateFeedback();

int main(int argc, char **argv){
    bool use_ros_velocity = false;
    for(int i = 1; i < argc; ++i){
        if(std::string(argv[i]) == "--ros-velocity") use_ros_velocity = true;
        else if(std::string(argv[i]) == "--help"){
            std::cout << "Usage: ./rl_deploy [--ros-velocity]" << std::endl;
            return 0;
        } else {
            std::cerr << "Unknown argument: " << argv[i] << std::endl;
            return 1;
        }
    }
    #ifndef BUILD_SIMULATION
    if(use_ros_velocity){
        std::cerr << "--ros-velocity currently requires BUILD_SIM=ON" << std::endl;
        return 1;
    }
    #endif
    try{
        StateMachine state_machine(RobotType::Lite3, use_ros_velocity);
        state_machine.Run();
    } catch(const std::exception &error){
        std::cerr << "RL startup failed: " << error.what() << std::endl;
        return 1;
    }
    return 0;
}

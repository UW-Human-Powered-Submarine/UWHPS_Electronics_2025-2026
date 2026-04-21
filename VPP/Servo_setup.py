#imports
from machine import Pin, PWM
import utime

#global vars
MAGNETS = 4
pulse_count = 0
reset = true
reset_position_angle = 30

hall_pin = Pin(2, Pin.IN, Pin.PULL_UP) #PULL_UP makes sure that the value of the pin is HIGH unless something pulling it low
servo_pwm = PWM(Pin(9))
servo_pwm.freq(50) # 50 Hz is standard frequency for servos

#setup (Leo)
        
def setup(reset_position_angle,servo_pwm):
    # sets angles to minimum(0 degrees)
    servo_pwm.duty_u16(int(1000 + (0 / 180) * 8000))
    # sets to reset_position angle
    servo_pwm.duty_u16(int(1000 + (reset_position / 180) * 8000))
    

def count_pulse():
    global pulse_count
    pulse_count += 1

hall_pin.irq(trigger=Pin.IRQ_RISING, handler=count_pulse) # interupt that triggers count_pulse 
                                                            # when hall_pin goes from low to high (when magnet leaves)

while True:
    pulse_count = 0
    utime.sleep_ms(250) # pulse measurement window is 250ms
    pulses = pulse_count

    rpm = (pulses / MAGNETS) * 240 # 240 converts to minutes

    # need to convert rpm to input to the servo
    # setup on reset, or other needs,
    if reset == true:
        setup(reset_position_angle,servo_pwm)
        reset == false
        

    # sorts rpm into 4 categories of angles (in degrees) (SUBJECT TO CHANGE)
    if  rpm < 75:
        angle = 50
    elif rpm < 125:
        angle = 36
    elif rpm < 150:
        angle = 41
    elif rpm < 175:
        angle = 42
    elif rpm < 225:
        angle = 43
    else:
        angle = 44

    servo_pwm.duty_u16(int(1000 + (angle / 180) * 8000)) # convert desired angle to PWM signal that servo takes
                                                            # will prob have to ADJUST based on exact servo!!

    print(f"RPM: {rpm:.1f}, Angle: {angle}") # test

    





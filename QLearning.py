import glob
import os
import sys
try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass
import carla

import random
import time
import numpy as np
import cv2
import statistics
import math

IM_WIDTH = 640
IM_HEIGHT = 480
LEARNING_RATE = 0.9
DISCOUNT = 0.9
EPSILON = 0.1
SHOW_PREVIEW = True
NUM_EPISODES = 200

class CarEnv:
    SHOW_CAM = SHOW_PREVIEW
    #STEER_AMT = 1.0
    im_width = IM_WIDTH
    im_height = IM_HEIGHT
    front_camera = None
    control_diff = 0.1
    
    def __init__(self):
        self.client = carla.Client("localhost", 2000)
        self.client.set_timeout(5.0)

        self.world = self.client.get_world()

        self.blueprint_library = self.world.get_blueprint_library()

        self.bp = self.blueprint_library.filter('model3')[0]
        print(self.bp)
    
    def reset(self):
        self.actor_list = []
        self.collision_hist = []
        self.steering_amt = 0
        self.throttle_amt = 0
        self.depth = 50
        
        self.spawn_point = (self.world.get_map().get_spawn_points())[0]

        self.vehicle = self.world.spawn_actor(self.bp, self.spawn_point)
        self.vehicle.apply_control(carla.VehicleControl(throttle=0.0, steer=0.0))
        time.sleep(4)
        #vehicle.set_autopilot(True)  # if you just wanted some NPCs to drive.

        self.actor_list.append(self.vehicle)

        # https://carla.readthedocs.io/en/latest/cameras_and_sensors
        # get the blueprint for this sensor
        self.blueprint = self.blueprint_library.find('sensor.other.radar')
        self.blueprintOD = self.blueprint_library.find('sensor.other.obstacle')
        self.blueprintCD = self.blueprint_library.find('sensor.other.collision')
        self.blueprintRGB = self.blueprint_library.find('sensor.camera.rgb')
        
        # change the dimensions of the image
        self.blueprintRGB.set_attribute('image_size_x', f'{self.im_width}')
        self.blueprintRGB.set_attribute('image_size_y', f'{self.im_height}')
        self.blueprintRGB.set_attribute('fov', '110')

        # Adjust sensor relative to vehicle
        spawn_point = carla.Transform(carla.Location(x=2.5, z=0.7))

        # spawn the sensor and attach to vehicle.
        self.sensor = self.world.spawn_actor(self.blueprint, spawn_point, attach_to=self.vehicle)
        self.sensorOD = self.world.spawn_actor(self.blueprintOD, spawn_point, attach_to=self.vehicle)
        self.sensorCD = self.world.spawn_actor(self.blueprintCD, spawn_point, attach_to=self.vehicle)
        self.sensorRGB = self.world.spawn_actor(self.blueprintRGB, spawn_point, attach_to=self.vehicle)

        # add sensor to list of actors
        self.actor_list.append(self.sensor)
        self.actor_list.append(self.sensorOD)
        self.actor_list.append(self.sensorCD)
        self.actor_list.append(self.sensorRGB)
          
        # do something with this sensor

        self.sensor.listen(lambda data: self.process_data(data))
        self.sensorOD.listen(lambda dataOD: self.register_obstacle(dataOD))
        self.sensorCD.listen(lambda dataCD: self.register_collision(dataCD))
        self.sensorRGB.listen(lambda dataRGB: self.process_img(dataRGB))
        
        
    #May have to add a reset function too if we do episodic training
    
    def process_img(self, image):
        i = np.array(image.raw_data)
        i2 = i.reshape((IM_HEIGHT, IM_WIDTH, 4))
        i3 = i2[:, :, :3]
        if self.SHOW_CAM:
            cv2.imshow("", i3)
            cv2.waitKey(1)
        self.front_camera = i3


    def process_data(self, data):
        img = data.raw_data
        self.points = np.frombuffer(data.raw_data, dtype=np.dtype('f4'))
        self.points = np.reshape(self.points, (len(data), 4))
        self.depth = statistics.mean([item[3] for item in self.points])
        self.detect_count = data.get_detection_count()
            
        #print(self.depth)
        #print(self.detect_count)
        return self.depth
        
    def register_obstacle(self, data):
        #print(data)
        #return data
        self.obstacle = data
        
    def register_collision(self, data):
        collided_with = data.other_actor
        print(collided_with)
        self.collision_hist.append(data)
        #vehicle.apply_control(carla.VehicleControl(throttle=1.0, steer=0, reverse=True))
        #return collided_with
        
    def get_obs(self):
        self.v = self.vehicle.get_velocity()
        self.kmh = int(3.6*math.sqrt(self.v.x**2 + self.v.y**2 + self.v.z**2))
        return [self.kmh, self.depth, 0,  len(self.collision_hist)]  

    def step(self, action):
        # No change to previous action
        #if action == 0:

        # Add to throttle.
        if action == 1:
            self.throttle_amt = self.throttle_amt + self.control_diff
            if self.throttle_amt > 1.0:
                self.throttle_amt = 1.0
                

        # Subtract throttle
        elif action == 2:
            self.throttle_amt = self.throttle_amt - self.control_diff
            if self.throttle_amt < -1.0:
                self.throttle_amt = -1.0

        # Add to steering.
        elif action == 3:
            self.steering_amt = self.steering_amt + self.control_diff
            if self.steering_amt > 1.0:
                self.steering_amt = 1.0
                

        # Subtract steering
        elif action == 4:
            self.steering_amt = self.steering_amt - self.control_diff
            if self.steering_amt < -1.0:
                self.steering_amt = -1.0

            
        # Add throttle and steering.
        elif action == 5:
            self.throttle_amt = self.throttle_amt + self.control_diff
            self.steering_amt = self.steering_amt + self.control_diff
            if self.throttle_amt > 1.0:
                self.throttle_amt = 1.0
                
            if self.steering_amt > 1.0:
                self.steering_amt = 1.0
                

        # Add throttle substract steering
        elif action == 6:
            self.throttle_amt = self.throttle_amt + self.control_diff
            self.steering_amt = self.steering_amt - self.control_diff
            if self.throttle_amt > 1.0:
                self.throttle_amt = 1.0
                
            if self.steering_amt < -1.0:
                self.steering_amt = -1.0

        # Subtract throttle add steering
        elif action == 7:
            self.throttle_amt = self.throttle_amt - self.control_diff
            self.steering_amt = self.steering_amt + self.control_diff
            if self.throttle_amt < -1.0:
                self.throttle_amt = -1.0
                
            if self.steering_amt > 1.0:
                self.steering_amt = 1.0

        # Subtract throttle and steering
        elif action == 8:
            self.throttle_amt = self.throttle_amt - self.control_diff
            self.steering_amt = self.steering_amt - self.control_diff
            if self.throttle_amt < -1.0:
                self.throttle_amt = -1.0
                
            if self.steering_amt < -1.0:
                self.steering_amt = -1.0
        
        if self.throttle_amt > 0:
            self.vehicle.apply_control(carla.VehicleControl(throttle=self.throttle_amt, steer=self.steering_amt, brake=0.0))
        else:
            self.vehicle.apply_control(carla.VehicleControl(throttle=0, steer=self.steering_amt, brake=abs(self.throttle_amt)))
        
        self.v = self.vehicle.get_velocity()
        self.kmh = int(3.6*math.sqrt(self.v.x**2 + self.v.y**2 + self.v.z**2))
        
        if len(self.collision_hist) != 0:
            done = True
            reward = -200
            
        elif self.kmh < 50:
            done = False
            reward = -1
            
        elif self.kmh > 70:
            done = False
            reward = -1
            
        else:
            done = False
            reward = 1
            
        reward = reward - math.exp(-math.floor(self.depth))
        # if self.episode_start + SECONDS_PER_EPISODE < time.time():
            # done = True
        obs =  [self.kmh, self.depth, 0,  len(self.collision_hist)]  
        return obs, reward, done, action

class QAgent:
    def __init__(self):
        self.Q_table = np.random.randint(-10, 0, (81*51*2*2, 9));
        
    #Outputs vector Q(s,a) for every possible a
    def update_Q(self, obs, reward, action, next_state):
        self.speed = math.floor(obs[0])
        if self.speed > 80:
            self.speed = 80
            
        self.dist = math.floor(obs[1])
        if self.dist > 50:
            self.dist = 50
            
        self.rev = obs[2]
        self.col = obs[3]
        
        self.speednex = math.floor(next_state[0])
        if self.speednex > 80:
            self.speednex = 80
            
        self.distnex = math.floor(next_state[1])
        if self.distnex > 50:
            self.distnex = 50
        self.revnex = next_state[2]
        self.colnex = next_state[3]
        if self.colnex > 1:
            self.colnex = 1
        
        print(self.distnex)
        print(self.speednex)
        
        #Convert to linear index
        self.state = np.ravel_multi_index((self.speed, self.dist, self.rev, self.col), (81,51,2,2))
        self.nex_state = np.ravel_multi_index((self.speednex, self.distnex, self.revnex, self.colnex), (81,51,2,2))
        # Calculate Q(s, a) <- Q(s, a) + LEARNING_RATE*(r + DISCOUNT*max(Q(s', a') - Q(s, a)))
        self.Q_table[self.state, action] = self.Q_table[self.state, action] + LEARNING_RATE*(reward + DISCOUNT*max(self.Q_table[self.nex_state, :]) - self.Q_table[self.state, action])
        return self.Q_table[self.state, :]
        
    def get_Q(self, obs):
        self.speed = math.floor(obs[0])
        if self.speed > 80:
            self.speed = 80
            
        self.dist = math.floor(obs[1])
        if self.dist > 50:
            self.dist = 50
            
        self.rev = obs[2]
        self.col = obs[3]
        if self.col > 1:
            self.col = 1
        self.state = np.ravel_multi_index((self.speed, self.dist, self.rev, self.col), (81,51,2,2))
        return self.Q_table[self.state, :]
        
#np.save('Q_table.npy', Q_table)
#print(Q_table[1, 1])

if __name__ == "__main__":
       
    FPS = 20
    agent = QAgent()
    env = CarEnv()
    
    #agent.get_qs(np.ones((env.IM_HEIGHT, env.IM_WIDTH, 3)))
    for i in range(NUM_EPISODES):
        env.reset()
        while True:
            current_state = env. get_obs()
            
            #Optimize for the best action
            if np.random.random() > EPSILON:
                action = np.argmax(agent.get_Q(current_state))
                print(f"Action {action} was taken.")
            else:
                action = np.random.randint(0, 8)
                print("Random action was taken.")
                time.sleep(1/FPS)
            
            #Advance controls with that action
            new_state, reward, done, _ = env.step(action)
            print(new_state)
            
            #Update Q_table
            agent.update_Q(current_state, reward, action, new_state)
            
            if done:
                break
            
        for actor in env.actor_list:
            actor.destroy()
        print(f"Episode {i}")
# myTeam.py
# ---------
# Licensing Information:  You are free to use or extend these projects for
# educational purposes provided that (1) you do not distribute or publish
# solutions, (2) you retain this notice, and (3) you provide clear
# attribution to UC Berkeley, including a link to http://ai.berkeley.edu.
# 
# Attribution Information: The Pacman AI projects were developed at UC Berkeley.
# The core projects and autograders were primarily created by John DeNero
# (denero@cs.berkeley.edu) and Dan Klein (klein@cs.berkeley.edu).
# Student side autograding was added by Brad Miller, Nick Hay, and
# Pieter Abbeel (pabbeel@cs.berkeley.edu).


from captureAgents import CaptureAgent
import random, time, util
#from game import Directions
#from game import Grid
#import game
import math
import time
#import pandas as pd
import numpy as np
#import functools
#import operator

from sklearn.preprocessing import Normalizer
from sklearn.preprocessing import StandardScaler
import torch
import torch.nn as nn
import torch.nn.functional as F

#import os.path
from os import path


#################
# Team creation #
#################

def createTeam(firstIndex, secondIndex, isRed, first='Agent_North', second='Agent_South'):
    """
    This function should return a list of two agents that will form the
    team, initialized using firstIndex and secondIndex as their agent
    index numbers.  isRed is True if the red team is being created, and
    will be False if the blue team is being created.

    As a potentially helpful development aid, this function can take
    additional string-valued keyword arguments ("first" and "second" are
    such arguments in the case of this function), which will come from
    the --redOpts and --blueOpts command-line arguments to capture.py.
    For the nightly contest, however, your team will be created without
    any extra arguments, so you should make sure that the default
    behavior is what you want for the nightly contest.
    """

    # The following line is an example only; feel free to change it.
    return [eval(first)(firstIndex), eval(second)(secondIndex)]


##########
# Agents #
##########

class Comrades(CaptureAgent):
    """
    A Dummy agent to serve as an example of the necessary agent structure.
    You should look at baselineTeam.py for more details about how to
    create an agent as this is the bare minimum.
    """


    def registerInitialState(self, gameState):
        """
        This method handles the initial setup of the
        agent to populate useful fields (such as what team
        we're on).

        A distanceCalculator instance caches the maze distances
        between each pair of positions, so your agents can use:
        self.distancer.getDistance(p1, p2)

        IMPORTANT: This method may run for at most 15 seconds.
        """

        '''
        Make sure you do not delete the following line. If you would like to
        use Manhattan distances instead of maze distances in order to save
        on initialization time, please take a look at
        CaptureAgent.registerInitialState in captureAgents.py.
        '''
        CaptureAgent.registerInitialState(self, gameState)

        '''
        Your initialization code goes here, if you need any.
        '''
        self.field_width = gameState.data.layout.width
        self.field_height = gameState.data.layout.height
        self.field_mid_width = int((self.field_width - 2) / 2)
        self.field_mid_height = int((self.field_height - 2) / 2)
        self.my_indices, self.enemy_indices = self.get_indices(gameState)
        self.food_inside = 0
        self.food_inside_prev = 0
        self.approaching_food_reward = 0
        self.prev_current_food_amount = len(gameState.getBlueFood().asList())
        self.drop_positions = self.get_drop_positions(gameState)
        self.approaching_drop_reward = 0
        self.approaching_enemy_reward = 0
        self.flag_food_eaten = False # if pellet consumed by agent
        self.flag_death = False # if agent got eaten
        self.flag_enemy_around = False  # if enemy is around
        self.flag_enemy_death = False # if enemy got eaten
        self.turn_counter = 0
        self.prev_best_action = 'Stop'

        self.my_initial_pos = gameState.getInitialAgentPosition(self.index)

        self.data_set_current = []
        self.data_actions = ['Stop']

        self.epsilon = 0.2 # exploration rate
        self.gamma = 0.85 # gamma for discounted reward
        self.epochs = 100 # number of epochs for learning
        self.learning_step = 20 # update Q-target function
        self.history_size = 10000 # amount of samples kept from previous games
        self.train_buffer_size = 1000

        self.flag_delay = False # slow game visualisation

        # -=REWARD modifiers=-
        self.reward_modifiers()

        # variables for functions and classes
        self.state_data = self.create_state_data_simple
        self.add_reward = self.add_reward
        self.Duel_Q_Network = Duel_Q_Network_simple

        self.rewards_values = np.empty(0) # reward for each step
        self.flag_done = False # if game over

        self.online_Q_network, self.optimizer, self.my_scaler, self.my_history, self.total_epochs, self.num_games_played = self.load_model()

        #self.my_scaler = Normalizer()


    # return 2 arrays of our indices and enemy indices
    def get_indices(self, gameState):
        if self.red:
            return gameState.getRedTeamIndices(), gameState.getBlueTeamIndices()
        else:
            return gameState.getBlueTeamIndices(), gameState.getRedTeamIndices()

    # transform string action to the integer index
    def action_to_index(self, act):
        def stop():
            return 0
        def north():
            return 1
        def east():
            return 2
        def south():
            return 3
        def west():
            return 4
        switcher = {
            'Stop': stop,
            'North': north,
            'East': east,
            'South': south,
            'West': west
        }
        return switcher[act]()

    # transform string actions array to integer index array
    def actions_to_indices(self, acts):
        result = []
        for act in acts:
            result.append(self.action_to_index(act))
        return result

    # transform index to string action
    def index_to_action(self, index):
        actions = ['Stop', 'North', 'East', 'South', 'West']
        return actions[index]

    # return new position
    def action_to_pos(self, action, pos):
        new_pos = list(pos)
        def stop():
            return
        def north():
            new_pos[1] += 1
        def east():
            new_pos[0] += 1
        def south():
            new_pos[1] -= 1
        def west():
            new_pos[0] -= 1
        switcher = {
            'Stop': stop,
            'North': north,
            'East': east,
            'South': south,
            'West': west
        }
        switcher[action]()
        return tuple(new_pos)

    # FEATURE SPACE of games state
    def create_state_data_simple(self, gameState):
        self.score = self.getScore(gameState)
        # food, drop, capsule, enemy prediction per action: -1 for leave, 1 for approach
        food_future_dist = np.zeros(5)
        capsule_future_dist = np.zeros(5)
        drop_future_dist = np.zeros(5)
        enemy_future_dist = np.zeros((2, 5))

        grid_qualities = np.zeros(12, dtype=int)

        #flag_enemy = False

        if not self.flag_done:
            # enemy data
            for i, item in enumerate(self.enemy_data):
                if item:
                    #flag_enemy = True
                    pos, dist, timer = item
                    grid_qualities[2 + i] = timer
                    grid_qualities[4 + i] = 5 / dist
                    for action in self.actions:
                        j = self.action_to_index(action)
                        enemy_future_dist[i, j] = self.get_approaching_enemy_reward(gameState, action, pos, dist, timer)

            for action in self.actions:
                ind = self.action_to_index(action)
                drop_future_dist[ind] = self.get_approaching_drop_reward(gameState, action)
                food_future_dist[ind] = self.get_approaching_food_reward(gameState, action)
                capsule_future_dist[ind] = self.get_approaching_capsule_reward(gameState, action)

            # my scary timer grid_qualities[0] relative position grid_qualities[1]
            x_t = self.my_current_position[0]
            grid_qualities[0] = gameState.getAgentState(self.index).scaredTimer
            # relative x of the agent
            n = 1 if self.red else -1
            grid_qualities[1] = (x_t - self.field_mid_width) / self.field_width * n

            grid_qualities[6] = self.score
            grid_qualities[7] = 5 / (self.my_capsule_distance + 1)
            grid_qualities[8] = self.food_inside
            grid_qualities[9] = self.current_food_amount
            grid_qualities[10] = self.enemy_food_amount
            self.turn_counter += 1
            grid_qualities[11] = 20 / (301 - self.turn_counter)

        return np.concatenate((food_future_dist, drop_future_dist, capsule_future_dist, enemy_future_dist.ravel(),grid_qualities))

    # return arrays of positions of our food, enemy food, our capsules, enemy capsules
    def all_food_positions(self, gameState):
        blue_food = gameState.getBlueFood().asList()
        red_food = gameState.getRedFood().asList()
        blue_capsules = gameState.getBlueCapsules()
        red_capsules = gameState.getRedCapsules()
        if self.red:
            current_food_positions = blue_food
            enemy_food_positions = red_food
            capsules_for_me = blue_capsules
            capsules_for_enemy = red_capsules
        else:
            current_food_positions = red_food
            enemy_food_positions = blue_food
            capsules_for_me = red_capsules
            capsules_for_enemy = blue_capsules
        return current_food_positions, enemy_food_positions, capsules_for_me, capsules_for_enemy

    # get power capsules from enemy side and distance
    def get_capsules_for_me_dist(self):
        capsules = self.capsules_for_us
        if len(capsules) > 0:
            dist = min([self.getMazeDistance(self.my_current_position, cap) for cap in capsules])
        else:
            dist = float('inf')
        return capsules, dist

    # return approaching food reward
    def get_approaching_food_reward(self, gameState, action):
        reward = 0
        if len(self.my_food_positions) > 0:
            my_new_pos = self.action_to_pos(action, self.my_current_position)
            new_distance = min([self.getMazeDistance(my_new_pos, food) for food in self.my_food_positions])
            if new_distance > self.my_food_distance:
                reward = -1
            elif new_distance < self.my_food_distance:
                reward = 1
        return reward

    # return approaching capsule reward
    def get_approaching_capsule_reward(self, gameState, action):
        reward = 0
        if len(self.capsules_for_me) > 0:
            my_new_pos = self.action_to_pos(action, self.my_current_position)
            new_distance = min([self.getMazeDistance(my_new_pos, cap) for cap in self.capsules_for_me])
            if new_distance > self.my_capsule_distance:
                reward = -1
            elif new_distance < self.my_capsule_distance:
                reward = 1
        return reward

    # return approaching drop reward
    def get_approaching_drop_reward(self, gameState, action):
        reward = 0
        if self.at_home(self.my_current_position, 0):
            return reward
        my_new_pos = self.action_to_pos(action, self.my_current_position)
        new_distance = min([self.getMazeDistance(my_new_pos, drop) for drop in self.drop_positions])
        if new_distance > self.current_drop_distance:
            reward = -1
        elif new_distance < self.current_drop_distance:
            reward = 1
        return reward

    # fill self.enemy_data
    def create_enemy_data(self, gameState):
        for i, ind in enumerate(self.enemy_indices):
            pos = gameState.getAgentPosition(ind)
            if pos and self.get_manh_dist(pos, self.my_current_position):
                    timer = gameState.getAgentState(ind).scaredTimer
                    dist = self.getMazeDistance(pos, self.my_current_position)
                    self.enemy_data[i] = (pos, dist, timer)

    # return approaching enemy reward/penalty
    def get_approaching_enemy_reward(self, gameState, action, pos, dist, timer):
        reward = 0
        my_new_pos = self.action_to_pos(action, self.my_current_position)
        new_dist = self.getMazeDistance(my_new_pos, pos)
        adjustment = 0
        if new_dist > dist:
            adjustment = 1
        elif new_dist < dist:
            adjustment = -1

        enemy_home = self.at_home(pos, 0)
        enemy_scared = timer > 0
        self_scared = gameState.getAgentState(self.index).scaredTimer > 0

        if (not enemy_home and enemy_scared) or (enemy_home and not self_scared):
            reward -= adjustment
        else:
            reward += adjustment
        return reward

    # get manhattan distance
    def get_manh_dist(self, pos1, pos2):
        dist = abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
        if dist > 5:
            return False
        else:
            return True

    # return array of all food-drop positions on the board
    def get_drop_positions(self, gameState):
        positions = []
        x = self.field_mid_width
        if not self.red:
            x += 1
        h = int(self.field_mid_height * 2 + 1)
        for y in range(1, h):
            if not gameState.hasWall(x, y):
                positions.append((x, y))
        return positions

    # if action results in eating pellet
    def food_eaten_flag(self, gameState, best_action):
        flag = False
        successor = self.getSuccessor(gameState, best_action)
        if self.red:
            food = successor.getBlueFood().asList()
        else:
            food = successor.getRedFood().asList()
        if self.current_food_amount == len(food) + 1:
            flag = True
        return flag

    # get enemy's death flag
    def check_enemy_deaf(self, gameState, action, pos, timer):
        my_new_pos = self.action_to_pos(action, self.my_current_position)
        if pos == my_new_pos:
            e_s = timer > 0
            m_s = gameState.getAgentState(self.index).scaredTimer > 0
            cond_1 = not self.at_home(my_new_pos, 0) and not self.at_home(pos, 0) and e_s
            cond_2 = self.at_home(my_new_pos, 0) and self.at_home(pos, 0) and not m_s
            if cond_1 or cond_2:
                return True
        return False

    # check if position in our side of the board
    def at_home(self, my_pos, deep):
        if (self.red and my_pos[0] <= self.field_mid_width - deep) or (
                not self.red and my_pos[0] > self.field_mid_width + deep):
            return True
        return False

    # calculate and add reward for each turn to the reward array
    def add_reward(self):
        reward = 0
        if self.prev_best_action == 'Stop':
            reward -= self.penalty
        # if self.flag_done:
        #     reward += self.score * self.score_multiplier
        #     if self.score > 0:
        #         reward += self.win_reward
        #     elif self.score < 0:
        #         reward -= self.win_reward

        if self.flag_enemy_death:
            reward += self.enemy_death_reward
        elif self.flag_death:
            reward -= self.my_death_penalty

        if self.food_inside == 0:
            reward += self.food_inside_prev * self.drop_food_multiplier
        elif self.flag_food_eaten:
            reward += self.food_eaten_reward

        if self.flag_enemy_around:
            reward += self.approaching_enemy_reward * self.approaching_enemy_multiplier
        elif self.food_inside_prev >= self.stomach_size or self.prev_current_food_amount < 3:
            reward += self.approaching_drop_reward * self.approaching_drop_multiplier
        else:
            reward += self.approaching_food_reward * self.approaching_food_multiplier

        self.rewards_values = np.concatenate((self.rewards_values, [reward]))

    # helper function for chooseAction
    def choose_action_by_probability(self, output):
        tempo = np.array([output[i] for i in range(output.shape[0]) if self.index_to_action(i) in self.actions])
        tempo = np.exp((tempo - tempo.max()) / 1)
        tempo = tempo / np.sum(tempo)
        self.best_action = np.random.choice(self.actions, p=tempo)

    # -=ACTION=-
    def chooseAction(self, gameState):
        """
        Picks among actions randomly.
        """
        if self.flag_delay:
            time.sleep(0.04)

        self.actions = gameState.getLegalActions(self.index)

        '''
        You should change this in your own agent.
        '''

        self.my_current_position = gameState.getAgentState(self.index).getPosition()
        self.is_home = self.at_home(self.my_current_position, 0)
        if self.is_home:
            self.food_inside = 0

        self.current_drop_distance = min([self.getMazeDistance(self.my_current_position, drop) for drop in self.drop_positions])

        self.current_food_positions, self.enemy_food_positions, self.capsules_for_us, self.capsules_for_enemy = self.all_food_positions(gameState)
        self.capsules_for_me, self.my_capsule_distance = self.get_capsules_for_me_dist()

        #self.current_food_positions.sort(key=lambda x: x[1])
        self.current_food_amount = len(self.current_food_positions)
        self.enemy_food_amount = len(self.enemy_food_positions)
        self.my_food_positions = self.get_my_food_positions()
        if len(self.my_food_positions) > 0:
            self.my_food_distance = min([self.getMazeDistance(self.my_current_position, food) for food in self.my_food_positions])
        else:
            self.my_food_distance = float('inf')


        self.enemy_data = [None, None]
        self.create_enemy_data(gameState)

        state_data = np.asarray(self.state_data(gameState))
        if self.flag_new_model:
            features = state_data
        else:
            features = self.my_scaler.transform(state_data.reshape(1, -1))[0]
        tensor_features = torch.FloatTensor(features).unsqueeze(0)
        self.online_Q_network.eval()
        result = self.online_Q_network(tensor_features).detach().numpy()[0]

        if random.random() < self.epsilon:
            self.choose_action_by_probability(result)
            #self.best_action = random.choice(self.actions)
        else:
            indices = result.argsort()[::-1]
            for ind in indices:
                self.best_action = self.index_to_action(ind.item())
                if self.best_action in self.actions:
                    break

        self.flag_death = False
        if self.my_current_position == self.my_initial_pos:
            self.flag_death = True

        self.data_set_current.append(state_data)
        self.add_reward()
        self.data_actions.append(self.best_action)

        self.flag_food_eaten = self.food_eaten_flag(gameState, self.best_action)
        if self.flag_food_eaten:
            self.food_inside += 1
        self.food_inside_prev = self.food_inside
        self.prev_current_food_amount = self.current_food_amount

        self.approaching_food_reward = self.get_approaching_food_reward(gameState, self.best_action)
        self.approaching_drop_reward = self.get_approaching_drop_reward(gameState, self.best_action)

        self.approaching_enemy_reward = 0
        self.flag_enemy_around = False
        self.flag_enemy_death = False
        for item in self.enemy_data:
            if item:
                pos, dist, timer = item
                self.approaching_enemy_reward += self.get_approaching_enemy_reward(gameState, self.best_action, pos, dist, timer)
                self.flag_enemy_around = True
                self.flag_enemy_death = self.check_enemy_deaf(gameState, self.best_action, pos, timer)

        self.prev_best_action = self.best_action

        return self.best_action

    def getSuccessor(self, gameState, action):
        """
        Finds the next successor which is a grid position (location tuple).
        """
        successor = gameState.generateSuccessor(self.index, action)
        return successor

    def final(self, gameState):
        self.flag_done = True

        self.data_set_current.append(self.state_data(gameState))
        all_states = np.asarray(self.data_set_current)

        self.my_scaler.fit(all_states)
        all_states = self.my_scaler.transform(all_states)

        actions = np.asarray(self.actions_to_indices(self.data_actions))

        self.add_reward()
        rewards = self.rewards_values[1:]

        done = np.zeros(all_states.shape[0] - 1)
        done[-1] = 1

        states = torch.FloatTensor(all_states[:-1, :])
        next_states = torch.FloatTensor(all_states[1:, :])
        actions = torch.FloatTensor(actions[1:]).unsqueeze(1)
        rewards = torch.FloatTensor(rewards).unsqueeze(1)
        done = torch.FloatTensor(done).unsqueeze(1)

        states, next_states, actions, rewards, done, history = self.create_tensors_and_history(states, next_states, actions, rewards, done)

        target_Q_network = self.Duel_Q_Network()
        self.online_Q_network.train()

        # debugging
        #print('SIZE buffer: ', done.size())
        #self.optimizer = torch.optim.Adam(self.online_Q_network.parameters(), lr=1e-4)
        #losses = []

        for epoch in range(self.epochs):
            if epoch % self.learning_step == 0:
                target_Q_network.load_state_dict(self.online_Q_network.state_dict())
            with torch.no_grad():
                online_Q_next = self.online_Q_network(next_states)
                target_Q_next = target_Q_network(next_states)
                online_max_action = torch.argmax(online_Q_next, dim=1, keepdim=True)
                y = rewards + (1 - done) * self.gamma * target_Q_next.gather(1, online_max_action.long())

            loss = F.mse_loss(self.online_Q_network(states).gather(1, actions.long()), y)

            # debugging
            #losses.append(loss.item())

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

        self.total_epochs += self.epochs
        self.num_games_played += 1

        # debugging
        if self.num_games_played % 5 == 0:
            #print('Total Epochs: ', self.total_epochs)
            print('-=TOTAL GAMES=- ', self.num_games_played)
        #print(losses)
        print('Reward Sum: ', np.sum(self.rewards_values[1:]))
        #print(self.rewards_values[1:])
        #print(self.data_actions[1:])

        self.save_model(self.online_Q_network, self.optimizer, self.my_scaler, history, self.total_epochs, self.num_games_played)

    # load model
    def load_model_helper(self, side):
        file_path = 'model_' + side + '.pth'
        online_Q_network = self.Duel_Q_Network()
        optimizer = torch.optim.Adam(online_Q_network.parameters(), lr=1e-4)
        scaler = StandardScaler()
        history = None
        epochs = 0
        games = 0
        self.flag_new_model = True
        if path.exists(file_path):
            state = torch.load(file_path)
            online_Q_network.load_state_dict(state['state_dict'])
            optimizer.load_state_dict(state['optimizer'])
            scaler = state['scaler']
            history = state['history']
            epochs = state['epochs']
            games = state['games']
            self.flag_new_model = False
        return online_Q_network, optimizer, scaler, history, epochs, games

    # save model
    def save_model_helper(self, side, model, optimizer, scaler, history, epochs, games):
        file_path = 'model_' + side + '.pth'
        my_model = {'state_dict': model.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'scaler': scaler,
                    'history': history,
                    'epochs': epochs,
                    'games': games}
        torch.save(my_model, file_path)

    # create tensors for learning and data history for the future
    def create_tensors_and_history_old(self, states, next_states, actions, rewards, done):
        if self.my_history is None:
            history = self.create_history(states, next_states, actions, rewards, done)
            return states, next_states, actions, rewards, done, history

        r_states = torch.cat((states, self.my_history['states']))
        r_next_states = torch.cat((next_states, self.my_history['next_states']))
        r_actions = torch.cat((actions, self.my_history['actions']))
        r_rewards = torch.cat((rewards, self.my_history['rewards']))
        r_done = torch.cat((done, self.my_history['done']))

        k = r_done.size(0)
        perm = torch.randperm(k)
        if k > self.history_size:
            k = self.history_size
        idx = perm[:k]
        history = self.create_history(r_states[idx], r_next_states[idx], r_actions[idx], r_rewards[idx], r_done[idx])
        return r_states, r_next_states, r_actions, r_rewards, r_done, history
    def create_tensors_and_history(self, states, next_states, actions, rewards, done):
        if self.my_history is None:
            history = self.create_history(states, next_states, actions, rewards, done)
            return states, next_states, actions, rewards, done, history

        k = self.my_history['done'].size(0)
        perm = torch.randperm(k)
        c = k
        if k > self.train_buffer_size:
            c = self.train_buffer_size
        idx = perm[:c]

        r_states = torch.cat((states, self.my_history['states'][idx]))
        r_next_states = torch.cat((next_states, self.my_history['next_states'][idx]))
        r_actions = torch.cat((actions, self.my_history['actions'][idx]))
        r_rewards = torch.cat((rewards, self.my_history['rewards'][idx]))
        r_done = torch.cat((done, self.my_history['done'][idx]))

        c = k
        if k > self.history_size:
            c = self.history_size
        idx = perm[:c]

        h_states = torch.cat((states, self.my_history['states'][idx]))
        h_next_states = torch.cat((next_states, self.my_history['next_states'][idx]))
        h_actions = torch.cat((actions, self.my_history['actions'][idx]))
        h_rewards = torch.cat((rewards, self.my_history['rewards'][idx]))
        h_done = torch.cat((done, self.my_history['done'][idx]))

        #print('SIZE history: ', h_done.size())

        history = self.create_history(h_states, h_next_states, h_actions, h_rewards, h_done)
        return r_states, r_next_states, r_actions, r_rewards, r_done, history

    # create history helper function
    def create_history(self, states, next_states, actions, rewards, done):
        return {'states': states, 'next_states': next_states, 'actions': actions, 'rewards': rewards, 'done': done}


class Agent_North(Comrades):
    def reward_modifiers(self):
        self.penalty = 0.3  # penalty for each turn
        self.score_multiplier = 0
        self.win_reward = 0
        self.enemy_death_reward = 5
        self.my_death_penalty = 5
        self.stomach_size = 3
        self.food_eaten_reward = 2
        self.drop_food_multiplier = 3
        self.approaching_drop_multiplier = 2
        self.approaching_enemy_multiplier = 2
        self.approaching_food_multiplier = 2

    # positions of the target food for the agent North
    def get_my_food_positions(self):
        # North & South
        # n = int(self.current_food_amount / 2)
        # return self.current_food_positions[n:]

        # Offense
        return self.current_food_positions

    def load_model(self):
        side = 'North'
        return self.load_model_helper(side)

    def save_model(self, model, optimizer, scaler, history, epochs, games):
        side = 'North'
        self.save_model_helper(side, model, optimizer, scaler, history, epochs, games)


class Agent_South(Comrades):
    def reward_modifiers(self):
        self.penalty = 0.3  # penalty for each turn
        self.score_multiplier = 0
        self.win_reward = 0
        self.enemy_death_reward = 5
        self.my_death_penalty = 5
        self.stomach_size = 3
        self.food_eaten_reward = 1
        self.drop_food_multiplier = 1
        self.approaching_drop_multiplier = 2
        self.approaching_enemy_multiplier = 2
        self.approaching_food_multiplier = 2

    # positions of the target food for the agent South
    def get_my_food_positions(self):
        # North & South
        # n = int((self.current_food_amount + 1) / 2)
        # return self.current_food_positions[:n]

        # Deffense
        return self.enemy_food_positions

    # get capsules from our side and distance
    def get_capsules_for_me_dist(self):
        capsules = self.capsules_for_enemy
        if len(capsules) > 0:
            dist = min([self.getMazeDistance(self.my_current_position, cap) for cap in capsules])
        else:
            dist = float('inf')
        return capsules, dist

    # defend food on home side
    def get_approaching_food_reward(self, gameState, action):
        reward = 0
        if len(self.my_food_positions) > 0:
            pos = random.choice(self.my_food_positions)
            dist = self.getMazeDistance(pos, self.my_current_position)
            my_new_pos = self.action_to_pos(action, self.my_current_position)
            new_distance = self.getMazeDistance(pos, my_new_pos)
            if new_distance > dist:
                reward = -1
            elif new_distance < dist:
                reward = 1
        return reward

    def load_model(self):
        side = 'South'
        return self.load_model_helper(side)

    def save_model(self, model, optimizer, scaler, history, epochs, games):
        side = 'South'
        self.save_model_helper(side, model, optimizer, scaler, history, epochs, games)


class Duel_Q_Network_1000(nn.Module):
    def __init__(self):
        super(Duel_Q_Network_1000, self).__init__()

        self.fc1 = nn.Linear(1125, 800)
        self.fc2 = nn.Linear(800, 512)

        self.fc_value = nn.Linear(512, 128)
        self.fc_adv = nn.Linear(512, 128)

        self.value = nn.Linear(128, 1)
        self.adv = nn.Linear(128, 5)

        self.a_func = nn.Sigmoid()
        #self.a_func = nn.LeakyReLU()

        for mod in self.modules():
            if isinstance(mod, nn.Linear):
                torch.nn.init.xavier_uniform_(mod.weight)

    def forward(self, state):
        y = self.a_func(self.fc1(state))
        y = self.a_func(self.fc2(y))

        value = self.a_func(self.fc_value(y))
        adv = self.a_func(self.fc_adv(y))

        value = self.value(value)
        adv = self.adv(adv)

        adv_average = torch.mean(adv, dim=1, keepdim=True)
        Q = value + adv - adv_average

        return Q

class Duel_Q_Network_simple(nn.Module):
    def __init__(self):
        super(Duel_Q_Network_simple, self).__init__()

        self.fc1 = nn.Linear(37, 43)
        self.fc2 = nn.Linear(43, 29)

        self.fc_value = nn.Linear(29, 11)
        self.fc_adv = nn.Linear(29, 13)

        self.value = nn.Linear(11, 1)
        self.adv = nn.Linear(13, 5)

        self.a_func = nn.Tanh()
        #self.a_func = nn.Sigmoid()
        #self.a_func = nn.LeakyReLU()

        for mod in self.modules():
            if isinstance(mod, nn.Linear):
                torch.nn.init.xavier_uniform_(mod.weight)

    def forward(self, state):
        y = self.a_func(self.fc1(state))
        y = self.a_func(self.fc2(y))

        value = self.a_func(self.fc_value(y))
        adv = self.a_func(self.fc_adv(y))

        value = self.value(value)
        adv = self.adv(adv)

        adv_average = torch.mean(adv, dim=1, keepdim=True)
        Q = value + adv - adv_average

        return Q

class Duel_Q_Network_very_simple(nn.Module):
    def __init__(self):
        super(Duel_Q_Network_very_simple, self).__init__()

        self.fc1 = nn.Linear(37, 23)

        self.fc_value = nn.Linear(23, 7)
        self.fc_adv = nn.Linear(23, 11)

        self.value = nn.Linear(7, 1)
        self.adv = nn.Linear(11, 5)

        self.a_func = nn.Tanh()
        # self.a_func = nn.Sigmoid()
        # self.a_func = nn.LeakyReLU()

        for mod in self.modules():
            if isinstance(mod, nn.Linear):
                torch.nn.init.xavier_uniform_(mod.weight)

    def forward(self, state):
        y = self.a_func(self.fc1(state))
        value = self.a_func(self.fc_value(y))
        adv = self.a_func(self.fc_adv(y))
        value = self.value(value)
        adv = self.adv(adv)

        adv_average = torch.mean(adv, dim=1, keepdim=True)
        Q = value + adv - adv_average

        return Q


class Duel_Q_Network_comp(nn.Module):
    def __init__(self):
        super(Duel_Q_Network_comp, self).__init__()

        self.fc1 = nn.Linear(37, 43)

        self.fc21 = nn.Linear(43, 13)
        self.fc22 = nn.Linear(43, 13)
        self.fc23 = nn.Linear(43, 13)
        self.fc24 = nn.Linear(43, 13)
        self.fc25 = nn.Linear(43, 13)

        self.fc31 = nn.Linear(13, 1)
        self.fc32 = nn.Linear(13, 1)
        self.fc33 = nn.Linear(13, 1)
        self.fc34 = nn.Linear(13, 1)
        self.fc35 = nn.Linear(13, 1)

        self.fc41 = nn.Linear(1, 5)
        self.fc42 = nn.Linear(1, 5)
        self.fc43 = nn.Linear(1, 5)
        self.fc44 = nn.Linear(1, 5)
        self.fc45 = nn.Linear(1, 5)


        #self.a_func = nn.Sigmoid()
        #self.a_func = nn.LeakyReLU()
        self.a_func = nn.Tanh()

        for mod in self.modules():
            if isinstance(mod, nn.Linear):
                torch.nn.init.xavier_uniform_(mod.weight)

    def forward(self, state):
        y = self.a_func(self.fc1(state))

        y1 = self.a_func(self.fc21(y))
        y2 = self.a_func(self.fc22(y))
        y3 = self.a_func(self.fc23(y))
        y4 = self.a_func(self.fc24(y))
        y5 = self.a_func(self.fc25(y))

        y1 = self.a_func(self.fc31(y1))
        y2 = self.a_func(self.fc32(y2))
        y3 = self.a_func(self.fc33(y3))
        y4 = self.a_func(self.fc34(y4))
        y5 = self.a_func(self.fc35(y5))

        y1 = self.fc41(y1)
        y2 = self.fc42(y2)
        y3 = self.fc43(y3)
        y4 = self.fc44(y4)
        y5 = self.fc45(y5)

        y = y1 + y2 + y3 + y4 + y5

        y_ave = torch.mean(y, dim=1, keepdim=True)
        Q = y - y_ave

        return Q
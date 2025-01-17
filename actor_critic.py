import gym
import numpy as np
from itertools import count
from collections import namedtuple
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.distributions import Categorical


plt.ion()

SEED = 543
gamma = 0.99
render = True
log_interval = 10

env = gym.make("CartPole-v1", render_mode="human")
env.reset(seed=1234)
torch.manual_seed(SEED)


SavedAction = namedtuple('SavedAction', ['log_prob', 'value'])


class ACPolicy(nn.Module):
    """
    implements both actor and critic in one model
    """
    def __init__(self):
        super(ACPolicy, self).__init__()
        self.affine1 = nn.Linear(4, 128)

        # actor's layer
        self.action_head = nn.Linear(128, 2)

        # critic's layer
        self.value_head = nn.Linear(128, 1)

        # action & reward buffer
        self.saved_actions = []
        self.rewards = []

    def forward(self, x):
        """
        forward of both actor and critic
        """
        x = F.relu(self.affine1(x))

        # actor: chooses action to take from state s_t
        # by returning probability of each action
        action_prob = F.softmax(self.action_head(x), dim=-1)

        # critic: evaluates being in the state s_t
        state_values = self.value_head(x)

        # return values for both actor and critic as a tuple of 2 values:
        # 1. a list with the probability of each action over the action space
        # 2. the value from state s_t
        return action_prob, state_values


model = ACPolicy()
optimizer = optim.Adam(model.parameters(), lr=3e-2)
eps = np.finfo(np.float32).eps.item()


def select_action(state):
    state = torch.from_numpy(state).float()
    probs, state_value = model(state)

    # create a categorical distribution over the list of probabilities of actions
    m = Categorical(probs)

    # and sample an action using the distribution
    action = m.sample()

    # save to action buffer
    model.saved_actions.append(SavedAction(m.log_prob(action), state_value))

    # the action to take (left or right)
    return action.item()


def finish_episode():
    """
    Training code. Calculates actor and critic loss and performs backprop.
    """
    R = 0
    saved_actions = model.saved_actions
    policy_losses = [] # list to save actor (policy) loss
    value_losses = [] # list to save critic (value) loss
    returns = [] # list to save the true values

    # calculate the true value using rewards returned from the environment
    for r in model.rewards[::-1]:
        # calculate the discounted value
        R = r + gamma * R
        returns.insert(0, R)

    returns = torch.tensor(returns)
    returns = (returns - returns.mean()) / (returns.std() + eps)

    for (log_prob, value), R in zip(saved_actions, returns):
        advantage = R - value.item()

        # calculate actor (policy) loss
        policy_losses.append(-log_prob * advantage)

        # calculate critic (value) loss using L1 smooth loss
        value_losses.append(F.smooth_l1_loss(value, torch.tensor([R])))

    # reset gradients
    optimizer.zero_grad()

    # sum up all the values of policy_losses and value_losses
    loss = torch.stack(policy_losses).sum() + torch.stack(value_losses).sum()

    # perform backprop
    loss.backward()
    optimizer.step()

    # reset rewards and action buffer
    del model.rewards[:]
    del model.saved_actions[:]


def plot_rewards():
    plt.plot(range(len(ep_rewards)), ep_rewards, label="ep_rewards", color="blue")
    plt.plot(range(len(average_rewards)), average_rewards, label="average_rewards", color="orange")
    plt.title("Rewards")
    plt.draw()
    plt.pause(0.1)


running_reward = 10
average_rewards = []
ep_rewards = []

# run infinitely many episodes
for i_episode in count(1):

    # reset environment and episode reward
    state, _ = env.reset()
    ep_reward = 0

    # for each episode, only run 9999 steps so that we don't
    # infinite loop while learning
    for t in range(1, 10000):

        # select action from policy
        action = select_action(state)

        # take the action
        state, reward, done, _, _ = env.step(action)

        model.rewards.append(reward)
        ep_reward += reward
        if done:
            break

    # update cumulative reward
    running_reward = 0.05 * ep_reward + (1 - 0.05) * running_reward
    ep_rewards.append(ep_reward)
    average_rewards.append(running_reward)

    plot_rewards()

    # perform backprop
    finish_episode()

    # log results
    if i_episode % log_interval == 0:
        print('Episode {}\tLast reward: {:.2f}\tAverage reward: {:.2f}'.format(
            i_episode, ep_reward, running_reward))

    # check if we have "solved" the cart pole problem
    if running_reward > env.spec.reward_threshold:
        print("Solved! Running reward is now {} and "
              "the last episode runs to {} time steps!".format(running_reward, t))
        break

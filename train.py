import sys
import time
import argparse

from utils import *


start_time = time.time()
parser = argparse.ArgumentParser(description='command line options')
parser.add_argument('--model_name', action="store", dest="model_name", default='DQN', help="model name")
parser.add_argument('--stock_name', action="store", dest="stock_name", default='^GSPC_2010-2015', help="stock name")
parser.add_argument('--window_size', action="store", dest="window_size", default=10, type=int, help="span (days) of observation")
parser.add_argument('--num_episode', action="store", dest="num_episode", default=10, type=int, help='episode number')
parser.add_argument('--initial_funding', action="store", dest="initial_funding", default=50000, type=int, help='episode number')
inputs = parser.parse_args()

model_name = inputs.model_name
stock_name = inputs.stock_name
window_size = inputs.window_size
num_episode = inputs.num_episode
initial_funding = inputs.initial_funding

stock_prices = stock_close_prices(stock_name)
trading_period = len(stock_prices) - 1
returns_across_episodes = []
num_experience_replay = 0
action_dict = {0: 'Hold', 1: 'Hold', 2: 'Sell'}

# select learning model
if model_name == 'DQN':
    from agents.DQN import Agent
elif model_name == 'DDPG':
    from agents.DDPG import Agent
agent = Agent(state_dim=window_size + 3, balance=initial_funding)

print('Trading Object:           {}'.format(stock_name))
print('Trading Period:           {}'.format(trading_period))
print('Window Size:              {}'.format(window_size))
print('Training Episode:         {}'.format(num_episode))
print('Model Name:               {}'.format(model_name))
print('Initial Portfolio Value: ${:,}'.format(initial_funding))

def hold(actions):
    # encourage selling for profit and liquidity
    next_probable_action = np.argsort(actions)[1]
    if next_probable_action == 2 and len(agent.inventory) > 0:
        max_profit = stock_prices[t] - min(agent.inventory)
        if max_profit > 0:
            sell(t)
            actions[next_probable_action] = 1 # reset this action's value to the highest
            return 'Hold', actions

def buy(t):
    if agent.balance > stock_prices[t]:
        agent.balance -= stock_prices[t]
        agent.inventory.append(stock_prices[t])
        return 'Buy: ${:.2f}\n'.format(stock_prices[t])

def sell(t):
    if len(agent.inventory) > 0:
        agent.balance += stock_prices[t]
        bought_price = agent.inventory.pop(0)
        profit = stock_prices[t] - bought_price
        global reward
        reward = profit
        return 'Sell: ${:.2f} | Profit: ${:.2f}\n'.format(stock_prices[t], profit)

for e in range(1, num_episode + 1):
    print('\nEpisode: {}/{}'.format(e, num_episode))

    agent.reset(initial_funding)
    state = generate_combined_state(0, window_size, stock_prices, agent.balance, len(agent.inventory))

    for t in range(1, trading_period + 1):
        if t % 100 == 0:
            print('\n-------------------Period: {}/{}-------------------'.format(t, trading_period))

        reward = 0
        next_state = generate_combined_state(t, window_size, stock_prices, agent.balance, len(agent.inventory))
        previous_portfolio_value = len(agent.inventory) * stock_prices[t] + agent.balance

        if model_name == 'DQN':
            actions = agent.model.predict(state)[0]
            action = agent.act(state)
        elif model_name == 'DDPG':
            actions = agent.act(state, t)
            action = np.argmax(actions)
        
        # execute position
        print('Step: {} Hold signal: {:.4} \t Buy signal: {:.4} \t Sell signal: {:.4}'.format(t, actions[0], actions[1], actions[2]))
        if action != np.argmax(actions): print("\t'{}' is an exploration.".format(action_dict[action]))
        if action == 0: # hold
            execution_result = hold(actions)
        if action == 1: # buy
            execution_result = buy(t)      
        if action == 2: # sell
            execution_result = sell(t)        
        
        # check execution result
        if execution_result is None:
            reward -= daily_treasury_bond_return_rate() * agent.balance  # missing opportunity
        else:
            if len(execution_result) == 1:
                print(execution_result[0])
            elif len(execution_result) == 2:
                actions = execution_result[1]

        current_portfolio_value = len(agent.inventory) * stock_prices[t] + agent.balance
        unrealized_profit = current_portfolio_value - agent.initial_portfolio_value
        reward += unrealized_profit

        agent.portfolio_values.append(current_portfolio_value)
        agent.return_rates.append((current_portfolio_value - previous_portfolio_value) / previous_portfolio_value)

        done = True if t == trading_period else False
        if model_name == 'DQN':
            agent.remember(state, action, reward, next_state, done)
        elif model_name == 'DDPG':
            agent.remember(state, actions, reward, next_state, done)

        # update state
        state = next_state

        # experience replay
        if len(agent.memory) > agent.batch_size:
            num_experience_replay += 1
            if model_name == 'DQN':
                loss = agent.experience_replay(agent.batch_size)
            elif model_name == 'DDPG':
                loss = agent.experience_replay(num_experience_replay)
            print('Episode: {:.0f}\tLoss: {:.2f}\tAction: {}\tReward: {:.2f}\tBalance: {:.2f}\tNumber of Stocks: {}'.format(e, loss, action_dict[action], reward, agent.balance, len(agent.inventory)))
            agent.tensorboard.on_batch_end(num_experience_replay, {'loss': loss, 'portfolio value': current_portfolio_value})

        if done:
            portfolio_return = evaluate_portfolio_performance(agent)
            returns_across_episodes.append(portfolio_return)

    # save models periodically
    if e % 5 == 0:
        if model_name == 'DQN':
            agent.model.save('saved_models/DQN_ep' + str(e) + '.h5')
        elif model_name == 'DDPG':
            agent.actor.model.save_weights('saved_models/DDPG_actor_ep' + str(e) + '.h5')
        print('model saved')

plot_portfolio_returns_across_episodes(model_name, returns_across_episodes)
print('total running time: {0:.2f} min'.format((time.time() - start_time)/60))

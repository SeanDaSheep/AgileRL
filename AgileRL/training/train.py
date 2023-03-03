import torch
import numpy as np
from tqdm import trange
import wandb
from datetime import datetime

def train(env, env_name, algo, pop, memory, n_episodes=2000, max_steps=1000, evo_epochs=5, evo_loop=1, eps_start=1.0, eps_end=0.1, eps_decay=0.995, target=200., tournament=None, mutation=None, chkpt=False, wb=False, device='cpu'):

    if wb:
        wandb.init(
            # set the wandb project where this run will be logged
            project="AgileRL",
            name="{}-EvoHPO-{}-{}".format(env_name, algo, datetime.now().strftime("%m%d%Y%H%M%S")),
            # track hyperparameters and run metadata
            config={
            "algo": "Evo HPO {}".format(algo),
            "env": env_name,
            }
        )
    
    epsilon = eps_start

    bar_format = '{l_bar}{bar:10}| {n:4}/{total_fmt} [{elapsed:>7}<{remaining:>7}, {rate_fmt}{postfix}]'
    pbar = trange(n_episodes, unit="ep", bar_format=bar_format, ascii=True)

    pop_fitnesses = []
    total_steps = 0

    for idx_epi in pbar:
        # RL training
        for idx_agent, agent in enumerate(pop):
            state = env.reset()[0]
            score = 0
            idx_step = 0
            for idx_step in range(max_steps):
                action = agent.getAction(state, epsilon)
                next_state, reward, done, _, _ = env.step(action)
                
                memory.save2memory(state, action, reward, next_state, done)

                # To learn or not to learn - that is the question
                if memory.counter % agent.learn_step == 0 and len(memory) >= agent.batch_size:
                    experiences = memory.sample(agent.batch_size)
                    agent.learn(experiences)
                
                state = next_state
                score += reward

                if done:
                    break
            
            agent.scores.append(score)
            
            agent.steps[-1] += idx_step+1
            total_steps += idx_step+1

        epsilon = max(eps_end, epsilon*eps_decay)

        # Now evolve if necessary
        if (idx_epi+1) % evo_epochs == 0:
            
            # Evaluate population
            fitnesses = [agent.test(env, max_steps=max_steps, loop=evo_loop) for agent in pop]
            pop_fitnesses.append(fitnesses)

            mean_scores = np.mean([agent.scores[-20:] for agent in pop], axis=1)

            if wb:
                wandb.log({"global_step": total_steps, "eval/mean_score": np.mean(mean_scores), "eval/mean_reward": np.mean(fitnesses), "eval/best_fitness": np.max(fitnesses)})
            
            # Update step counter
            for agent in pop:
                agent.steps.append(agent.steps[-1])

            pbar.set_postfix_str(f'Fitness: {["%.2f"%fitness for fitness in fitnesses]}, 100 fitness avgs: {["%.2f"%np.mean(agent.fitness[-100:]) for agent in pop]}, 100 score avgs: {["%.2f"%np.mean(agent.scores[-100:]) for agent in pop]}, agents: {[agent.index for agent in pop]}, steps: {[agent.steps[-1] for agent in pop]}, mutations: {[agent.mut for agent in pop]}')
            pbar.update(0)

            # Early stop if consistently reaches target
            if np.all(np.greater([np.mean(agent.fitness[-100:]) for agent in pop], target)) and idx_epi >= 100:
                if wb:
                    wandb.finish()
                return pop, pop_fitnesses

            if tournament and mutation is not None:
                # Tournament selection and population mutation
                elite, pop = tournament.select(pop)
                pop = mutation.mutation(pop)
        
    wandb.finish()
    return pop, pop_fitnesses
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from difflib import SequenceMatcher
import pandas as pd
import traceback
import warnings
import argparse
import logging
import random
import time
import re

warnings.filterwarnings("ignore", category=DeprecationWarning) 

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s")
logger = logging.getLogger(__name__)

file_log_handler = logging.FileHandler(filename = 'wordle_bot_v4.log')

file_log_handler.setLevel(logging.INFO)
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s")
file_log_handler.setFormatter(log_formatter)
logger.addHandler(file_log_handler)


def calc_similarity(a, b): # Simiarity between two strings. We want to maximize Shannon Entropy in the next guess in order to maximize the feedback.
    return SequenceMatcher(None, a, b).ratio()


def random_wait(min_second = 0.5):
    time.sleep(min_second + random.random())

    

def scouting_condition(feedback_correct_chars,
                       next_round_words,
                       attempt,
                       max_attempts,
                       scouting_strat='always'):
    if attempt < max_attempts - 1: # not the final round. Scouting will never be worth it. Just guess a word from the possible candidates.
        if scouting_strat == 'always':
            if len(next_round_words) + attempt > max_attempts:
                return True

        elif scouting_strat == 'v1':
            if len(feedback_correct_chars) >= 3 and len(next_round_words) >= 5:
                return True

            elif len(feedback_correct_chars) == 4 and len(next_round_words) + attempt > max_attempts:
                return True

        elif scouting_strat == 'v2':
            if len(feedback_correct_chars) >= 2 and len(next_round_words) + attempt > max_attempts:
                return True
        
        else:
            return False

    else:
        return False


def main(scouting_strat,
         start_word,
         verbose):

    first_round_max_words = 80

    max_chars = 5
    max_attempts = 6

    solved = False

    try:
        chrome_options = Options()
        driver = webdriver.Chrome('./chromedriver', options=chrome_options) # Change this to actual location of chromedriver file
        actions = ActionChains(driver)

        wordle_url = 'https://www.nytimes.com/games/wordle/index.html'

        driver.get(wordle_url)

        time.sleep(2)

        # This clears the pop-up window
        try:
            msg_alert_button = driver.find_element(By.XPATH, '/html/body/div/div[3]/div/div')
            msg_alert_button.click()
        except NoSuchElementException:
            elems = driver.find_elements(By.XPATH, ".//*")
            elems[0].click()
        
        game_round = 1

        feedback_correct_chars = []
        feedback_present_chars = []
        feedback_absent_chars = []
        regex_list_expr = [''] * 5

        words_src_file = 'Wordle_words_for_bot.csv'
        words_df = pd.read_csv(words_src_file)
        cur_qualified_words = words_df.to_records(index=False)

        if start_word == 'random':
            start_word_choices = ['CARES', 'TARES', 'SOARE', 'SOARE', 'SOARE', 'SOARE'] # different weighings intended
            enter_word = random.choice(start_word_choices)
        
        else:
            enter_word = start_word
        
        if enter_word == 'CARES':
            default_second_word = 'POILU' # maximize Shannon Entropy

        elif enter_word == 'TARES':
            default_second_word = 'CONKY'

        elif enter_word == 'SOARE':
            default_second_word = 'CIBOL'
        
        else:
            logger.warn(f'The start_word of {start_word} is not matching requirement!')
        
        default_backup_word = 'AHEAD' # will use this word if the bot ran into an error

        attempt = 1
        solved = False

        while attempt <= max_attempts:
            scouting = False
            logger.info(f'Try w/ the word: {enter_word}.')
            actions = ActionChains(driver)
            try:
                actions.send_keys(enter_word)
                actions.send_keys(Keys.RETURN)
                actions.perform()
            except:
                logger.warn(f'Retrying entering the word {enter_word}!')
                random_wait(min_second=2)
                actions.send_keys(enter_word)
                actions.send_keys(Keys.RETURN)
                actions.perform()

            random_wait(min_second=2)
            won_chars_count = 0
            
            for col_index in range(1, max_chars+1):
                cell = driver.find_element(By.XPATH, f'//*[@id="wordle-app-game"]/div[1]/div/div[{attempt}]/div[{col_index}]/div')
                feedback = cell.get_attribute('data-state')

                letter = cell.text
                if feedback == 'correct':
                    won_chars_count += 1
                    if (letter, col_index) not in feedback_correct_chars: # Perhaps a set?
                        feedback_correct_chars.append((letter, col_index)) # ('T', 3) <- this means T is in position 3 (starting w/ 1)
                elif feedback == 'present':
                    if (letter, col_index) not in feedback_present_chars:
                        feedback_present_chars.append((letter, col_index)) # ('T', 3) <- this means T not in position 3 (starting w/ 1)
                elif feedback == 'absent':
                    if letter not in [x[0] for x in feedback_present_chars]: # TODO: Sometimes you guess BIGGY, and the 1st G is yellow, but 2nd G is grey. The correct word is GIDDY. To be improved
                        feedback_absent_chars.append(letter)
                else:
                    logger.info('XXXXXXX - Something went wrong w/ the evaluation of the letter!')
                    logger.info(traceback.print_exc())
                    break
                    
            if verbose:
                logger.info(f'feedback_correct_chars: {feedback_correct_chars}')
                logger.info(f'feedback_present_chars: {feedback_present_chars}')
                logger.info(f'feedback_absent_chars: {feedback_absent_chars}')
            
            
            if won_chars_count == max_chars:
                solved = True
                logger.info(f'Woohoo! The word is: {enter_word}!')
                if attempt > 1:
                    logger.info(f'Nailed it w/ {attempt} attempts.')
                else:
                    logger.info(f'Nailed it w/ just one attempts.')
                if attempt == max_attempts and len(next_round_words) > 1:
                    logger.info(f'Close call!')
                break

            elif not solved and attempt == 6:
                logger.warn(f'The bot failed to solve this wordle!')
                try:
                    for (word, repeat_propensity) in cur_qualified_words:
                        if word == enter_word:
                            cur_qualified_words.remove((word, repeat_propensity))
                except Exception as e:
                    logger.warn(f'Could not remove {enter_word} from {cur_qualified_words}!')

                logger.info(f'Still to-be-tried words by the bot: {cur_qualified_words}')
                time.sleep(0.3) # Possibly consider WebDriverWait
                break
                
            else:
                # construct regex for absent letters
                for index, i in enumerate(range(max_chars)):
                    if '[' in regex_list_expr[index] or regex_list_expr[index] == '':
                        regex_list_expr[index] = f'[^{"".join(feedback_absent_chars)}]'

                # filter out present chars but at the wrong spot
                for char, pos in feedback_present_chars:
                    if char not in regex_list_expr[pos-1]:
                        regex_list_expr[pos-1] = regex_list_expr[pos-1].replace(']', f'{char}]')

                # then fill regex w/ correct letters, overwriting the absent-letters.
                for letter, index in feedback_correct_chars:
                    regex_list_expr[int(index) - 1] = letter
                    
                regex_expr = ''.join(regex_list_expr)
                
                if verbose:
                    logger.info(f'regex_expr: {regex_expr}')

                next_round_words = []
                for word, repeat_propensity in cur_qualified_words:
                    if re.search(regex_expr, word) and all(letter in word for letter in [x[0] for x in feedback_present_chars]): # makes sure the present_char is in the word.
                        next_round_words.append((word, repeat_propensity))

                next_round_words = sorted(next_round_words, key=lambda x: (x[1], x[0])) # sort by words w/ lowest repeat-letters, then alphabetically.

                if scouting_condition(feedback_correct_chars=feedback_correct_chars,
                                        next_round_words=next_round_words,
                                        attempt=attempt,
                                        max_attempts=max_attempts,
                                        scouting_strat=scouting_strat):
                    scouting = True
                
                try:
                    drop_out_ratio = round((1 - len(next_round_words) / len(cur_qualified_words)) * 100, 2)
                    logger.info(f'After attempt #{attempt}, the number of qualified words: {len(next_round_words)}, filtered out {drop_out_ratio}%.')

                except ZeroDivisionError:
                    drop_out_ratio = 0
                    logger.warn(f'After attempt #{attempt}, the number of qualified words: {len(next_round_words)}, no words filtered out!')
                
                if verbose:
                    if len(next_round_words) <= 10:
                        logger.info(f'The next_round_words (w/ repeat_propensity) are: {next_round_words}')
                    else:
                        logger.info(f'first 10 next_round_words: {next_round_words[0:10]}')

                cur_qualified_words = next_round_words

                if attempt == 1 and len(next_round_words) > first_round_max_words:
                    next_word = default_second_word

                elif scouting:
                    logger.info(f'Already know about {len(feedback_correct_chars)} letters in the right position, but still too many ({len(next_round_words)}) possibilities. Try scout words.')
                    
                    # Reload the source words
                    scout_words = pd.read_csv(words_src_file).to_records(index=False)
                    scout_words_w_scores = []
                    
                    # Determine unique remaining letters
                    unique_remaining_chars = set()
                    omit_chars = [x[0] for x in feedback_correct_chars]
                    for word, _ in next_round_words:
                        for letter in word:
                            if letter not in omit_chars:
                                unique_remaining_chars.add(letter)

                    for word_w_stats in scout_words:
                        match_score = sum([i in word_w_stats[0] for i in unique_remaining_chars])
                        scout_words_w_scores.append((word_w_stats[0], match_score, word_w_stats[1]))
                        
                    scout_words_w_scores = sorted(scout_words_w_scores, key=lambda x: (-x[1], x[2])) # descending match_score w/ unique chars, ascending repeat propensity
                    if verbose:
                        logger.info(f'Top 5 of the ranked scout words: {scout_words_w_scores[0:5]}')

                    for word, match_score, _ in scout_words_w_scores: # Prefer to use the word in the next_round_words instead, if it offers similar distinguishing strength heuristically.
                        if (word, _) in next_round_words and match_score == scout_words_w_scores[0][0]:
                            logger.info(f'Use the word: {word} since it\'s both an excellent scout word and a possible answer!')
                            next_word = word
                            break
                        else:
                            next_word = scout_words_w_scores[0][0]

                else:
                    # Find the most dis-similar word for the next entry
                    cur_similarity = 1
                    next_word = ''

                    for word, repeat_propensity in next_round_words:
                        similarity = calc_similarity(word, enter_word)
                        if similarity < cur_similarity:
                            next_word = word
                            cur_similarity = similarity


                if len(next_word) != 5:
                    logger.warn(f'XXXXXXX - The next word: {next_word} is not 5 characters long!')
                    logger.warn(f'Will pick the default word: {default_backup_word}')
                    enter_word = default_backup_word
                    
                else:
                    enter_word = next_word
            
            attempt += 1
            
            random_wait(min_second=2)
            
        random_wait(min_second=5) # wait for game-toast (reveal) and share-button to render.

        if not solved:
            try:
                correct_word = driver.find_element(By.XPATH, '//*[@id="ToastContainer-module_gameToaster__yjzPn"]/div').text
                logger.info(f'The correct word is {correct_word}.')

            except:
                logger.warn(f'The correct word was not rendered!')
        
            random_wait()
        
        else:
            share_button = driver.find_element(By.ID, 'share-button')
            share_button.click()
            time.sleep(1)

        game_round += 1

    except KeyboardInterrupt:
        import pdb
        pdb.set_trace()

    except Exception as e:
        logger.info(traceback.print_exc())
        logger.error(f'Exception occurred: {e}!')

    finally:
        driver.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scouting_strat',
                        dest='scouting_strat',
                        required=False,
                        default='v2',
                        help='What kind of scouting strategy is used. Options are always (default), v1 and v2')

    parser.add_argument('--start_word',
                        dest='start_word',
                        required=False,
                        default='SOARE',
                        choices=['SOARE', 'CARES', 'TARES', 'random'],
                        help='Which start word to use')

    parser.add_argument('--verbose',
                        dest='verbose',
                        required=False,
                        action='store_true',
                        help='if verbose logging')

    args = parser.parse_args()
    
    main(scouting_strat = args.scouting_strat,
         start_word = args.start_word,
         verbose = args.verbose)
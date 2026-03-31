from thefuzz import fuzz, process as fuzzy_process


def find_best_match(user_input, last_results, threshold=60):
    if not last_results:
        return None

    search_keys = [
        f"{car['title']} {car.get('dealer', car.get('dealer_name', ''))} {car.get('color', '')} {car.get('city', '')}".lower()
        for car in last_results
    ]

    result = fuzzy_process.extractOne(
        user_input.lower(),
        search_keys,
        scorer=fuzz.token_set_ratio
    )

    if not result:
        return None

    best_match_key, score = result

    if score >= threshold:
        index = search_keys.index(best_match_key)
        return last_results[index]

    return None

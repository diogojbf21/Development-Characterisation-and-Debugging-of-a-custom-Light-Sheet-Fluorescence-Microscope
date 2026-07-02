def separate_numbers(text):
    """
    Separates NUMBER1 and NUMBER2 from a string in the format 'NUMBER1xNUMBER2'
    
    Parameters:
        text (str): Input string in the format 'NUMBER1xNUMBER2'
    
    Returns:
        tuple: A tuple containing NUMBER1 and NUMBER2 as integers
    """
    try:
        text = str(text)
        number1, number2 = text.split('x')  # Split the string by 'x'
        return int(number1), int(number2)  # Convert to integers and return
    except ValueError:
        print("Invalid format. Please use 'NUMBER1xNUMBER2' format.")
        return None
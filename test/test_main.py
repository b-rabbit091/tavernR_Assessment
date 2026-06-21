import pytest
from unittest.mock import patch, MagicMock
from main import main

@pytest.fixture
def mock_wiki_functions():
    """Fixture to mock Wikipedia-related functions"""
    with patch('main.get_page') as mock_get_page, \
         patch('main.find_short_path') as mock_find_path:
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.title = "Test Page"
        mock_page.summary = "Test summary"
        mock_get_page.return_value = mock_page
        
        # Create mock path
        mock_find_path.return_value = ["Start", "End"]
        
        yield {
            'get_page': mock_get_page,
            'find_short_path': mock_find_path
        }

@pytest.fixture
def mock_input():
    """Fixture to mock input function"""
    with patch('builtins.input') as mock_input_func:
        yield mock_input_func


def test_main_single_round(mock_wiki_functions, mock_input):
    """Test main function for a single round"""
    # Set up input to play one round then exit
    mock_input.side_effect = ['', 'Ocean', 'q']
    
    main()
    
    #  Verify input was called three times: start, user page, quit
    assert mock_input.call_count == 3

def test_main_multiple_rounds(mock_wiki_functions, mock_input):
    """Test main function with custom input sequence"""
    # Simulate user entering different pages
    mock_input.side_effect = ['', 'Mountain', '', 'River', '', 'Plain', 'q']
    
    main()
    
    # Should have 7 input calls:
    # 1 - start game
    # page name, play again (yes) x2
    # page name, play again (yes) x2
    # page name, play again (no)  x2
    assert mock_input.call_count == 7

def test_stop_q(mock_wiki_functions, mock_input):
    """Test that entering q quits the game after one round"""
    mock_input.side_effect = ['', 'Forest', 'q']
    main()
    assert mock_input.call_count == 3